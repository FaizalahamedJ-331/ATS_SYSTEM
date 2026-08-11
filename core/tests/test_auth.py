from django.core import mail
from django.core.cache import cache
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.email_utils import make_verification_token


@override_settings(
    SIGNUP_RATE_LIMIT=100,
    RESEND_RATE_LIMIT=100,
    # test_unverified_user_cannot_log_in POSTs to login — keep the default
    # 5-failure login budget from ever tripping here.
    LOGIN_RATE_LIMIT=100,
    LOGIN_IP_RATE_LIMIT=100,
)
class SignupTests(TestCase):
    def setUp(self):
        # The shared LocMemCache survives between tests, so rate-limit state
        # must not leak across tests.
        cache.clear()

    def _signup(self, username="alexm", email="alex@example.com"):
        return self.client.post(reverse("signup"), {
            "first_name": "Alex",
            "last_name": "Morgan",
            "email": email,
            "username": username,
            "password1": "SuperSecret42!",
            "password2": "SuperSecret42!",
        })

    def test_signup_page_renders(self):
        resp = self.client.get(reverse("signup"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Create your account")
        self.assertContains(resp, "Recruiter")

    def test_signup_creates_recruiter_and_redirects_to_check_inbox(self):
        resp = self._signup()
        self.assertRedirects(resp, reverse("verify_email_sent"))
        user = User.objects.get(username="alexm")
        self.assertFalse(user.is_superuser, "signups must never be admins")
        self.assertFalse(user.is_staff)
        self.assertEqual(user.email, "alex@example.com")
        self.assertTrue(user.is_active)
        # Not logged in yet — email verification comes first
        self.assertFalse(resp.wsgi_request.user.is_authenticated)
        self.assertFalse(user.profile.email_verified)

    def test_signup_sends_welcome_email_with_link(self):
        self._signup()
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Welcome to TalentPulse", msg.subject)
        self.assertEqual(msg.to, ["alex@example.com"])
        # The verification link points at the verify route
        user = User.objects.get(username="alexm")
        token = make_verification_token(user.pk)
        self.assertIn(reverse("verify_email", args=[token]), msg.body)
        self.assertIn(reverse("verify_email", args=[token]), msg.alternatives[0][0])

    def test_verify_email_activates_account(self):
        self._signup()
        user = User.objects.get(username="alexm")
        token = make_verification_token(user.pk)
        resp = self.client.get(reverse("verify_email", args=[token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Email verified!")
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.email_verified)
        # Now the user can log in
        ok = self.client.login(username="alexm", password="SuperSecret42!")
        self.assertTrue(ok)

    def test_verify_email_invalid_token(self):
        self._signup()
        resp = self.client.get(reverse("verify_email", args=["not-a-real-token"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "invalid or expired")
        user = User.objects.get(username="alexm")
        self.assertFalse(user.profile.email_verified)

    def test_verify_email_already_verified(self):
        self._signup()
        user = User.objects.get(username="alexm")
        token = make_verification_token(user.pk)
        self.client.get(reverse("verify_email", args=[token]))
        resp = self.client.get(reverse("verify_email", args=[token]))
        self.assertContains(resp, "Already verified")

    def test_unverified_user_cannot_log_in(self):
        self._signup()
        resp = self.client.post(reverse("login"), {
            "username": "alexm",
            "password": "SuperSecret42!",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please verify your email")
        self.assertContains(resp, "Resend link")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_resend_verification(self):
        self._signup()
        self.client.post(reverse("verify_email_resend"), {"email": "alex@example.com"})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Welcome to TalentPulse", mail.outbox[1].subject)

    def test_resend_does_not_leak_account_existence(self):
        self._signup()
        resp = self.client.post(reverse("verify_email_resend"), {"email": "nobody@example.com"})
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)
        # Same friendly message, no new email
        self.assertEqual(len(mail.outbox), 1)

    def test_signup_duplicate_email_rejected(self):
        User.objects.create_user("taken", "dup@example.com", "pw12345678x")
        resp = self.client.post(reverse("signup"), {
            "first_name": "A", "last_name": "B",
            "email": "DUP@example.com",  # case-insensitive
            "username": "fresh",
            "password1": "SuperSecret42!",
            "password2": "SuperSecret42!",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already exists")
        self.assertFalse(User.objects.filter(username="fresh").exists())

    def test_signup_duplicate_username_rejected(self):
        User.objects.create_user("dupe", "x@example.com", "pw12345678x")
        resp = self.client.post(reverse("signup"), {
            "first_name": "A", "last_name": "B",
            "email": "y@example.com",
            "username": "dupe",
            "password1": "SuperSecret42!",
            "password2": "SuperSecret42!",
        })
        self.assertEqual(resp.status_code, 200)

    def test_signup_redirects_authenticated_users(self):
        self.client.force_login(User.objects.create_user("busy", "b@example.com", "pw12345678x"))
        resp = self.client.get(reverse("signup"))
        self.assertRedirects(resp, "/")


class RoleAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", "boss@example.com", "pw12345678x")
        self.recruiter = User.objects.create_user(
            "hunter", "hunter@example.com", "pw12345678x",
            first_name="Hunt", last_name="Er",
        )

    def test_login_page_has_signup_link(self):
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Create your account")
        self.assertContains(resp, reverse("signup"))

    def test_anonymous_blocked_from_users(self):
        resp = self.client.get(reverse("user_list"))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('user_list')}")

    def test_recruiter_blocked_from_users(self):
        self.client.force_login(self.recruiter)
        resp = self.client.get(reverse("user_list"))
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "403", status_code=403)
        self.assertContains(resp, "Not your role", status_code=403)

    def test_recruiter_can_use_recruiting_pages(self):
        self.client.force_login(self.recruiter)
        for url in ("/", "/jobs/", "/candidates/", "/pipeline/", "/interviews/"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)

    def test_admin_can_manage_users(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.recruiter.get_username())

    def test_user_list_role_filter_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user_list") + "?role=admin")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "boss@example.com")
        self.assertNotContains(resp, "hunter@example.com")

    def test_user_list_role_filter_recruiter(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user_list") + "?role=recruiter")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "hunter@example.com")
        self.assertNotContains(resp, "boss@example.com")

    def test_user_list_status_filter(self):
        self.recruiter.is_active = False
        self.recruiter.save()
        self.client.force_login(self.admin)
        # Disabled filter shows only the disabled account
        resp = self.client.get(reverse("user_list") + "?status=disabled")
        self.assertContains(resp, "hunter@example.com")
        self.assertNotContains(resp, "boss@example.com")
        # Active filter hides it
        resp2 = self.client.get(reverse("user_list") + "?status=active")
        self.assertNotContains(resp2, "hunter@example.com")
        self.assertContains(resp2, "boss@example.com")

    def test_user_list_combined_filters(self):
        other_admin = User.objects.create_superuser("sec", "sec@example.com", "pw12345678x")
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user_list") + "?role=admin&status=active")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "boss@example.com")
        self.assertContains(resp, "sec@example.com")
        self.assertNotContains(resp, "hunter@example.com")

    def test_user_list_invalid_filter_ignored(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user_list") + "?role=hacker&status=whatever")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "boss@example.com")
        self.assertContains(resp, "hunter@example.com")

    def test_promote_recruiter_to_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("user_toggle_role", args=[self.recruiter.pk]))
        self.assertRedirects(resp, reverse("user_list"), fetch_redirect_response=False)
        self.recruiter.refresh_from_db()
        self.assertTrue(self.recruiter.is_superuser)
        self.assertTrue(self.recruiter.is_staff)

    def test_demote_back_to_recruiter(self):
        self.recruiter.is_superuser = True
        self.recruiter.is_staff = True
        self.recruiter.save()
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle_role", args=[self.recruiter.pk]))
        self.recruiter.refresh_from_db()
        self.assertFalse(self.recruiter.is_superuser)

    def test_cannot_change_own_role(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("user_toggle_role", args=[self.admin.pk]))
        self.assertRedirects(resp, reverse("user_list"), fetch_redirect_response=False)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser, "self-demotion must be blocked")
        # The error message is delivered on the redirected page
        page = self.client.get(reverse("user_list"))
        self.assertContains(page, "cannot change your own role")

    def test_recruiter_cannot_escalate_role(self):
        """A recruiter POSTing to toggle endpoints must get 403 (privilege escalation)."""
        self.client.force_login(self.recruiter)
        resp = self.client.post(reverse("user_toggle_role", args=[self.recruiter.pk]))
        self.assertEqual(resp.status_code, 403)
        self.recruiter.refresh_from_db()
        self.assertFalse(self.recruiter.is_superuser, "self-promotion must be blocked")

    def test_recruiter_cannot_disable_others(self):
        self.client.force_login(self.recruiter)
        resp = self.client.post(reverse("user_toggle_active", args=[self.admin.pk]))
        self.assertEqual(resp.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_second_admin_can_be_demoted_safely(self):
        """Demoting another admin is fine as long as the actor remains Admin."""
        other = User.objects.create_superuser("other", "other@example.com", "pw12345678x")
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle_role", args=[other.pk]))
        other.refresh_from_db()
        self.assertFalse(other.is_superuser)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser, "actor stays Admin, workspace keeps an Admin")

    def test_deactivate_and_reactivate(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle_active", args=[self.recruiter.pk]))
        self.recruiter.refresh_from_db()
        self.assertFalse(self.recruiter.is_active)
        # Deactivated users can no longer log in
        self.client.logout()
        ok = self.client.login(username="hunter", password="pw12345678x")
        self.assertFalse(ok)
        # Admin re-enables
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle_active", args=[self.recruiter.pk]))
        self.recruiter.refresh_from_db()
        self.assertTrue(self.recruiter.is_active)

    def test_cannot_deactivate_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle_active", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_role_toggle_requires_post(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("user_toggle_role", args=[self.recruiter.pk]))
        self.assertEqual(resp.status_code, 405)


@override_settings(SIGNUP_RATE_LIMIT=2, SIGNUP_RATE_WINDOW=3600, RESEND_RATE_LIMIT=2, RESEND_RATE_WINDOW=900)
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def _signup_payload(self, username, email):
        return {
            "first_name": "Alex", "last_name": "Morgan",
            "email": email, "username": username,
            "password1": "SuperSecret42!", "password2": "SuperSecret42!",
        }

    def test_signup_limited_per_ip(self):
        # 2 allowed, 3rd blocked (default 127.0.0.1 test client IP)
        ok1 = self.client.post(reverse("signup"), self._signup_payload("rluser1", "rl1@example.com"))
        ok2 = self.client.post(reverse("signup"), self._signup_payload("rluser2", "rl2@example.com"))
        blocked = self.client.post(reverse("signup"), self._signup_payload("rluser3", "rl3@example.com"))
        self.assertEqual(ok1.status_code, 302)
        self.assertEqual(ok2.status_code, 302)
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Too many attempts", status_code=429)
        self.assertTrue(blocked["Retry-After"], "429 should carry a Retry-After header")
        self.assertFalse(User.objects.filter(username="rluser3").exists())

    def test_signup_limit_resets_with_new_ip(self):
        # A different IP is on a fresh window
        self.client.post(reverse("signup"), self._signup_payload("rluser1", "rl1@example.com"))
        self.client.post(reverse("signup"), self._signup_payload("rluser2", "rl2@example.com"))
        blocked = self.client.post(reverse("signup"), self._signup_payload("rluser3", "rl3@example.com"))
        self.assertEqual(blocked.status_code, 429)
        # Same client, spoofed REMOTE_ADDR
        self.client.post(
            reverse("signup"),
            self._signup_payload("rluser4", "rl4@example.com"),
            REMOTE_ADDR="203.0.113.7",
        )
        self.assertTrue(User.objects.filter(username="rluser4").exists(), "new IP not throttled")

    def test_resend_limited_per_ip_and_email(self):
        # Sign up a real pending account first (bypass rate limit by clearing)
        cache.clear()
        self.client.post(
            reverse("signup"),
            self._signup_payload("pendrl", "pendrl@example.com"),
        )
        url = reverse("verify_email_resend")
        ok1 = self.client.post(url, {"email": "pendrl@example.com"})
        ok2 = self.client.post(url, {"email": "pendrl@example.com"})
        blocked = self.client.post(url, {"email": "pendrl@example.com"})
        self.assertEqual(ok1.status_code, 302)
        self.assertEqual(ok2.status_code, 302)
        self.assertEqual(blocked.status_code, 429)

    def test_resend_different_email_not_throttled(self):
        # A different submitted address is a separate bucket
        url = reverse("verify_email_resend")
        self.client.post(url, {"email": "a@example.com"})
        self.client.post(url, {"email": "a@example.com"})
        ok = self.client.post(url, {"email": "b@example.com"})
        self.assertEqual(ok.status_code, 302, "different address should not share the limit")

    def test_get_requests_not_counted(self):
        # GET on signup (the form) is never rate-limited
        for _ in range(5):
            resp = self.client.get(reverse("signup"))
            self.assertEqual(resp.status_code, 200)

    def test_window_expiry_resets_limit(self):
        from django.test.utils import override_settings as _os
        # Sign up twice, then simulate the window elapsing by clearing cache
        self.client.post(reverse("signup"), self._signup_payload("rluser1", "rl1@example.com"))
        self.client.post(reverse("signup"), self._signup_payload("rluser2", "rl2@example.com"))
        self.assertEqual(
            self.client.post(reverse("signup"), self._signup_payload("rluser3", "rl3@example.com")).status_code,
            429,
        )
        cache.clear()  # window expired
        ok = self.client.post(reverse("signup"), self._signup_payload("rluser3b", "rl3b@example.com"))
        self.assertEqual(ok.status_code, 302, "fresh window allows signup again")


@override_settings(
    LOGIN_RATE_LIMIT=2,
    LOGIN_IP_RATE_LIMIT=4,
    LOGIN_RATE_WINDOW=900,
)
class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "target", "target@example.com", "CorrectPass123!"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def _login(self, username="target", password="WrongPass999!", ip=None):
        kwargs = {}
        if ip:
            kwargs["REMOTE_ADDR"] = ip
        return self.client.post(
            reverse("login"), {"username": username, "password": password}, **kwargs
        )

    def test_brute_force_throttled_per_username(self):
        # 2 failed attempts allowed, 3rd blocked with 429 + Retry-After.
        self.assertEqual(self._login().status_code, 200)  # wrong pw, form re-renders
        self.assertEqual(self._login().status_code, 200)
        blocked = self._login()
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Too many attempts", status_code=429)
        self.assertTrue(blocked["Retry-After"], "429 must carry Retry-After")

    def test_different_username_not_throttled(self):
        # Failing on 'target' must not lock 'someoneelse'.
        self._login()
        self._login()
        blocked = self._login()
        self.assertEqual(blocked.status_code, 429)
        ok = self._login(username="someoneelse")
        self.assertEqual(ok.status_code, 200, "different username has its own bucket")

    def test_successful_login_resets_counter(self):
        self._login()
        self._login()
        blocked = self._login()
        self.assertEqual(blocked.status_code, 429)
        # Real user logs in successfully from the same IP → counters reset.
        ok = self.client.post(
            reverse("login"),
            {"username": "target", "password": "CorrectPass123!"},
        )
        self.assertEqual(ok.status_code, 302, "correct credentials must still work")
        # The authenticated client is now logged in; log out to test the
        # counters as an anonymous user again.
        self.client.logout()
        # Fresh failures allowed again — the success cleared the bucket.
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._login().status_code, 429)

    def test_per_ip_cap_blocks_username_spraying(self):
        # LOGIN_IP_RATE_LIMIT=4: five different usernames from one IP → 5th blocked.
        for name in ["a", "b", "c", "d"]:
            self.assertEqual(self._login(username=name).status_code, 200, name)
        blocked = self._login(username="e")
        self.assertEqual(blocked.status_code, 429)

    def test_per_ip_cap_is_per_ip(self):
        for name in ["a", "b", "c", "d"]:
            self._login(username=name)
        blocked = self._login(username="e")
        self.assertEqual(blocked.status_code, 429)
        # A different source IP has a fresh spray budget.
        ok = self._login(username="f", ip="203.0.113.99")
        self.assertEqual(ok.status_code, 200, "different IP not throttled")

    def test_get_requests_not_counted(self):
        for _ in range(10):
            resp = self.client.get(reverse("login"))
            self.assertEqual(resp.status_code, 200)
        # GETs never consumed any budget.
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._login().status_code, 429)


@override_settings(
    LOGIN_RATE_LIMIT=100,
    LOGIN_IP_RATE_LIMIT=100,
    ACCOUNT_LOCKOUT_LIMIT=3,
    ACCOUNT_LOCKOUT_WINDOW=900,
    ACCOUNT_LOCKOUT_COOLDOWN=900,
)
class AccountLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "victim", "victim@example.com", "CorrectPass123!"
        )
        self.user.profile.email_verified = True
        self.user.profile.save(update_fields=["email_verified"])

    def _fail(self, username="victim", ip=None):
        kwargs = {"REMOTE_ADDR": ip} if ip else {}
        return self.client.post(
            reverse("login"),
            {"username": username, "password": "WrongPass999!"},
            **kwargs,
        )

    def _succeed(self, username="victim"):
        return self.client.post(reverse("login"), {
            "username": username, "password": "CorrectPass123!"
        })

    def test_locks_account_after_threshold(self):
        # 3 failures allowed, 4th sees the lockout notice (not a 429).
        for _ in range(3):
            self.assertEqual(self._fail().status_code, 200)
        locked = self._fail()
        self.assertEqual(locked.status_code, 200)
        self.assertContains(locked, "temporarily locked")
        self.assertContains(locked, "minute")

    def test_lockout_counts_across_all_ips(self):
        # Failures from different IPs still accumulate on the same account.
        for ip in ["10.0.0.1", "10.0.0.2", "10.0.0.3"]:
            self.assertEqual(self._fail(ip=ip).status_code, 200)
        locked = self._fail(ip="10.0.0.4")
        self.assertEqual(locked.status_code, 200)
        self.assertContains(locked, "temporarily locked")

    def test_correct_password_unlocks_during_lockout(self):
        for _ in range(4):
            self._fail()
        # The real owner can always get in — lockout only stops wrong guesses.
        ok = self._succeed()
        self.assertEqual(ok.status_code, 302)
        self.assertRedirects(ok, "/", fetch_redirect_response=False)
        # Log back out to test the counters anonymously.
        self.client.logout()
        # Lockout cleared: failures get a fresh budget.
        for _ in range(3):
            self.assertEqual(self._fail().status_code, 200)
        locked = self._fail()
        self.assertContains(locked, "temporarily locked")

    def test_lockout_is_per_account(self):
        for _ in range(4):
            self._fail()
        # A different account is unaffected by victim's lockout.
        other = User.objects.create_user(
            "neighbor", "neighbor@example.com", "pw12345678x"
        )
        other.profile.email_verified = True
        other.profile.save(update_fields=["email_verified"])
        ok = self.client.post(reverse("login"), {
            "username": "neighbor", "password": "pw12345678x"
        })
        self.assertEqual(ok.status_code, 302, "other account must not be locked")

    def test_lockout_expires_after_cooldown(self):
        for _ in range(4):
            self._fail()
        self.assertContains(self._fail(), "temporarily locked")
        # Simulate the cooldown elapsing.
        from core.ratelimit import cache as _cache  # noqa: F401
        _cache.set(
            "rl:lockout:victim",
            {"hits": [], "locked_until": 0},
            60,
        )
        # Fresh budget again.
        for _ in range(3):
            self.assertEqual(self._fail().status_code, 200)
        self.assertContains(self._fail(), "temporarily locked")
