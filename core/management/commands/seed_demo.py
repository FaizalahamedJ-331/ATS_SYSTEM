"""
Seed the database with a realistic demo dataset:

    python manage.py seed_demo [--flush]

Creates a superuser (admin / admin12345), ~9 job openings, ~28 candidates with
auto-generated resumes (parsed by the real parser), applications across every
pipeline stage, rule-based screening results, and interviews.

Idempotent: safe to run repeatedly (existing records are skipped).
"""
import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from candidates.models import Application, Candidate, Resume
from interviews.models import Interview
from jobs.models import Job

random.seed(42)

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
JOBS = [
    {
        "title": "Senior Python Backend Engineer",
        "department": "Engineering", "location": "Remote (EU)", "employment_type": "full_time",
        "experience_level": "senior", "min_salary": 110000, "max_salary": 145000, "status": "open",
        "required_skills": ["Python", "Django", "PostgreSQL", "Docker", "AWS"],
        "nice_to_have_skills": ["Redis", "Kubernetes", "Celery", "GraphQL"],
        "description": "We are looking for a Senior Python Backend Engineer to own the design and delivery of high-traffic services powering our recruitment platform. You will work in a small autonomous team, ship frequently, and mentor junior engineers.",
        "responsibilities": "Design and build scalable REST APIs\nLead architecture decisions for core services\nImprove performance and reliability of critical endpoints\nMentor and code-review peers\nCollaborate with product on roadmap delivery",
        "requirements": "5+ years of professional Python development\nStrong SQL and data-modeling skills\nExperience operating services in AWS\nExcellent communication skills",
    },
    {
        "title": "Full-Stack JavaScript Developer",
        "department": "Engineering", "location": "Berlin, Germany", "employment_type": "full_time",
        "experience_level": "mid", "min_salary": 75000, "max_salary": 95000, "status": "open",
        "required_skills": ["JavaScript", "React", "Node.js", "TypeScript", "PostgreSQL"],
        "nice_to_have_skills": ["Next.js", "GraphQL", "Docker", "Tailwind"],
        "description": "Join our product team to build delightful user experiences for candidates and recruiters. You will own features end-to-end, from database schema to polished UI.",
        "responsibilities": "Develop new features across the stack\nWrite clean, tested TypeScript code\nOptimize frontend performance and accessibility\nParticipate in design reviews",
        "requirements": "3+ years building web applications\nProduction experience with React\nComfortable writing SQL",
    },
    {
        "title": "Data Scientist",
        "department": "Data", "location": "London, UK", "employment_type": "full_time",
        "experience_level": "mid", "min_salary": 85000, "max_salary": 110000, "status": "open",
        "required_skills": ["Python", "Machine Learning", "SQL", "Pandas", "Statistics"],
        "nice_to_have_skills": ["TensorFlow", "NLP", "Airflow", "Experimentation"],
        "description": "We are building predictive screening models that help companies hire better. You will work on the matching models that power our ATS scoring engine.",
        "responsibilities": "Build and evaluate ML models for candidate-job matching\nRun A/B experiments and analyze results\nOwn feature pipelines and data quality\nPresent findings to stakeholders",
        "requirements": "Strong statistics fundamentals\n3+ years of applied ML experience\nProficiency in Python and SQL",
    },
    {
        "title": "DevOps Engineer",
        "department": "Engineering", "location": "Amsterdam, Netherlands", "employment_type": "full_time",
        "experience_level": "mid", "min_salary": 80000, "max_salary": 100000, "status": "open",
        "required_skills": ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "CI/CD"],
        "nice_to_have_skills": ["Jenkins", "Grafana", "Python", "Prometheus"],
        "description": "Own our cloud infrastructure and delivery pipelines. You will keep our platform fast, reliable, and secure as we scale.",
        "responsibilities": "Manage AWS infrastructure with Terraform\nOperate Kubernetes clusters\nBuild and maintain CI/CD pipelines\nImprove observability with Prometheus and Grafana",
        "requirements": "Strong Linux fundamentals\nHands-on Kubernetes experience\nInfrastructure-as-code mindset",
    },
    {
        "title": "Product Designer",
        "department": "Design", "location": "Remote (Global)", "employment_type": "full_time",
        "experience_level": "mid", "min_salary": 70000, "max_salary": 90000, "status": "open",
        "required_skills": ["Figma", "UI/UX", "Wireframing", "Design Systems", "User Research"],
        "nice_to_have_skills": ["Prototyping", "Accessibility", "Adobe XD", "Illustrator"],
        "description": "Design the interface of our screening platform — workflows, dashboards and reporting. You will run research, prototype concepts, and ship a coherent design system.",
        "responsibilities": "Own end-to-end product design for new features\nRun user research and usability tests\nMaintain and evolve the design system\nPartner closely with engineering and product",
        "requirements": "Strong portfolio showing shipped products\nExpert Figma skills\nExperience with user testing",
    },
    {
        "title": "Digital Marketing Manager",
        "department": "Marketing", "location": "New York, USA", "employment_type": "full_time",
        "experience_level": "mid", "min_salary": 82000, "max_salary": 105000, "status": "open",
        "required_skills": ["SEO", "SEM", "Content Marketing", "Google Analytics", "Social Media"],
        "nice_to_have_skills": ["Email Marketing", "CRM", "Growth", "Branding"],
        "description": "Drive qualified candidate traffic to our product. You will own the full-funnel marketing strategy and report on performance weekly.",
        "responsibilities": "Plan and execute multi-channel campaigns\nOwn SEO roadmap and content calendar\nManage paid acquisition budgets\nAnalyze performance with GA4 and optimize",
        "requirements": "5+ years in digital marketing\nHands-on SEO and SEM experience\nData-driven with strong reporting skills",
    },
    {
        "title": "Talent Acquisition Specialist",
        "department": "People", "location": "Dublin, Ireland", "employment_type": "full_time",
        "experience_level": "junior", "min_salary": 45000, "max_salary": 60000, "status": "open",
        "required_skills": ["Recruitment", "Interviewing", "Onboarding", "Sourcing", "HRIS"],
        "nice_to_have_skills": ["Employee Relations", "Compensation", "ATS", "Employer Branding"],
        "description": "Support hiring across engineering, design and go-to-market teams. You will own the end-to-end recruitment process for a portfolio of roles.",
        "responsibilities": "Source and screen candidates\nCoordinate interview loops\nManage offer processes and onboarding\nBuild a strong candidate experience",
        "requirements": "1+ years in recruitment or HR\nExcellent organizational skills\nFamiliarity with an HRIS or ATS",
    },
    {
        "title": "Financial Analyst",
        "department": "Finance", "location": "Austin, USA", "employment_type": "full_time",
        "experience_level": "junior", "min_salary": 65000, "max_salary": 82000, "status": "open",
        "required_skills": ["Excel", "Financial Modeling", "Budgeting", "Reporting", "SQL"],
        "nice_to_have_skills": ["Forecasting", "Tableau", "ERP", "Accounting"],
        "description": "Partner with leadership to model growth, manage budgets and produce board-level reporting. Great first step into strategic finance.",
        "responsibilities": "Build and maintain financial models\nOwn the monthly close and reporting cycle\nSupport annual budgeting and forecasting\nAnalyze KPIs with SQL and Excel",
        "requirements": "Strong Excel and modeling skills\nBasic SQL ability\nAttention to detail",
    },
    {
        "title": "Sales Account Executive",
        "department": "Sales", "location": "Remote (US)", "employment_type": "full_time",
        "experience_level": "mid", "min_salary": 70000, "max_salary": 90000, "status": "open",
        "required_skills": ["SaaS Sales", "Lead Generation", "CRM", "Negotiation", "Account Management"],
        "nice_to_have_skills": ["Salesforce", "Demos", "Growth", "Prospecting"],
        "description": "Own the full sales cycle for mid-market accounts. You will demo our product, negotiate deals, and grow existing accounts.",
        "responsibilities": "Hunt and close new business\nRun product demos and POCs\nManage pipeline in Salesforce\nExpand revenue in assigned accounts",
        "requirements": "3+ years in B2B SaaS sales\nConsistent quota attainment\nStrong closing skills",
    },
]

CANDIDATES = [
    # (first, last, email, phone, city, headline, company, years, education, source, skills, summary, resume body)
    ("Aisha", "Khan", "aisha.khan@example.com", "+1 415 555 0123", "San Francisco, CA", "Senior Backend Engineer", "Stripe", 8,
     "M.Sc. Computer Science, Stanford University", "linkedin",
     ["Python", "Django", "PostgreSQL", "Docker", "AWS", "Redis", "Kubernetes", "System Design", "Microservices"],
     "Distributed systems engineer with 8 years building high-scale payment and analytics platforms.",
     "I am a backend engineer with 8 years of experience. I have deep expertise in Python, Django, PostgreSQL, Docker, AWS, Redis, Kubernetes, and microservices architecture. Recently I led the migration of a payments platform to Kubernetes and cut p99 latency by 40%. I hold an M.Sc. in Computer Science from Stanford University and enjoy mentoring junior engineers."),
    ("Mateo", "Rivera", "mateo.rivera@example.com", "+34 612 555 0188", "Madrid, Spain", "Backend Developer", "Glovo", 4,
     "B.S. Computer Science, Universidad Politécnica de Madrid", "job_board",
     ["Python", "Django", "PostgreSQL", "Docker", "Celery", "Redis"],
     "Backend developer focused on Python services, APIs and data pipelines.",
     "Backend developer with 4 years of experience building REST APIs in Python and Django. Proficient with PostgreSQL, Docker, Celery and Redis for job processing and caching. B.S. in Computer Science from Universidad Politécnica de Madrid."),
    ("Lucas", "Weber", "lucas.weber@example.com", "+49 151 555 0142", "Berlin, Germany", "Full-Stack Developer", "Personio", 5,
     "B.Sc. Informatics, TU Munich", "referral",
     ["JavaScript", "TypeScript", "React", "Node.js", "PostgreSQL", "Next.js", "GraphQL", "Docker"],
     "Full-stack engineer shipping product features end to end with React and Node.",
     "Full-stack developer with 5 years of experience. I build features end-to-end with TypeScript, React, Node.js and PostgreSQL. I have shipped several Next.js applications and GraphQL APIs used by thousands of users. I studied Informatics at TU Munich."),
    ("Priya", "Nair", "priya.nair@example.com", "+91 98 555 01234", "Bengaluru, India", "Frontend Engineer", "Zeta", 3,
     "B.Tech Computer Science, IIT Madras", "linkedin",
     ["JavaScript", "TypeScript", "React", "Tailwind", "HTML/CSS"],
     "Frontend engineer passionate about accessible, polished user interfaces.",
     "Frontend engineer with 3 years of experience building accessible interfaces with React, TypeScript and Tailwind CSS. I care deeply about detail, performance and a11y. B.Tech in Computer Science from IIT Madras."),
    ("Sofia", "Lindgren", "sofia.lindgren@example.com", "+46 70 555 0199", "Stockholm, Sweden", "Data Scientist", "Klarna", 6,
     "M.Sc. Statistics, Stockholm University", "website",
     ["Python", "Machine Learning", "SQL", "Pandas", "Statistics", "NLP", "Experimentation", "TensorFlow"],
     "Applied data scientist building models that drive product decisions.",
     "Data scientist with 6 years of applied experience in machine learning and statistics. I build models in Python with Pandas, scikit-learn and TensorFlow, run A/B experiments, and analyze large datasets with SQL. M.Sc. in Statistics from Stockholm University."),
    ("James", "O'Connor", "james.oconnor@example.com", "+353 87 555 0177", "Dublin, Ireland", "ML Engineer", "Intercom", 4,
     "M.Sc. Machine Learning, University College Dublin", "job_board",
     ["Python", "Machine Learning", "TensorFlow", "Pandas", "SQL", "Airflow", "NLP"],
     "ML engineer focused on NLP and applied deep learning.",
     "ML engineer with 4 years of experience in NLP and deep learning. I have deployed TensorFlow models to production and built Airflow pipelines for training data. M.Sc. in Machine Learning from University College Dublin."),
    ("Chen", "Wei", "chen.wei@example.com", "+86 138 5555 0166", "Shanghai, China", "Data Analyst", "Alibaba Cloud", 3,
     "B.S. Applied Mathematics, Fudan University", "event",
     ["Python", "SQL", "Excel", "Pandas", "Data Analysis", "Tableau"],
     "Data analyst turning raw data into clear business insight.",
     "Data analyst with 3 years of experience in data analysis and reporting. I use SQL, Python and Excel daily, build dashboards in Tableau, and communicate insights clearly. B.S. in Applied Mathematics from Fudan University."),
    ("Emily", "Zhang", "emily.zhang@example.com", "+1 206 555 0111", "Seattle, WA", "Site Reliability Engineer", "Amazon", 7,
     "B.S. Computer Science, University of Washington", "linkedin",
     ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "CI/CD", "Grafana", "Prometheus", "Bash"],
     "SRE who loves automation, reliability and clean infrastructure.",
     "Site reliability engineer with 7 years of experience running large AWS workloads. I manage Kubernetes clusters, write Terraform, and built the CI/CD pipelines that ship hundreds of deploys a day. Proficient in Linux, Bash, Grafana and Prometheus."),
    ("Rahul", "Mehta", "rahul.mehta@example.com", "+44 7700 555 012", "London, UK", "Cloud Engineer", "Monzo", 4,
     "B.E. Computer Engineering, Imperial College London", "agency",
     ["AWS", "Docker", "Kubernetes", "Linux", "Terraform", "Python"],
     "Cloud engineer helping teams run reliable services on AWS.",
     "Cloud engineer with 4 years of experience on AWS. I have built Kubernetes-based platforms with Terraform and am comfortable with Linux, Docker and Python scripting."),
    ("Nadia", "Haddad", "nadia.haddad@example.com", "+33 6 55 55 01 20", "Paris, France", "Product Designer", "Doctolib", 5,
     "M.A. Interaction Design, École de Design Nantes", "referral",
     ["Figma", "UI/UX", "Wireframing", "Design Systems", "User Research", "Prototyping", "Accessibility"],
     "Product designer crafting intuitive tools for complex workflows.",
     "Product designer with 5 years of experience in SaaS. I run user research, prototype in Figma, and maintain design systems. My work emphasizes accessibility and clarity. M.A. in Interaction Design from École de Design Nantes."),
    ("Tom", "Bennett", "tom.bennett@example.com", "+1 312 555 0134", "Chicago, IL", "UX Designer", "Duolingo", 3,
     "B.F.A. Graphic Design, School of the Art Institute of Chicago", "website",
     ["Figma", "UI/UX", "Wireframing", "Prototyping", "User Research"],
     "UX designer with a portfolio of research-driven product work.",
     "UX designer with 3 years of experience. I conduct user interviews, create wireframes and high-fidelity prototypes in Figma, and validate designs through usability testing. B.F.A. in Graphic Design."),
    ("Ingrid", "Johansson", "ingrid.johansson@example.com", "+46 8 555 0105", "Gothenburg, Sweden", "Marketing Manager", "Volvo Cars", 6,
     "M.Sc. Business Administration, Gothenburg University", "linkedin",
     ["SEO", "SEM", "Content Marketing", "Google Analytics", "Social Media", "Email Marketing", "Branding", "CRM"],
     "Growth marketing leader with a track record of compounding channel wins.",
     "Marketing manager with 6 years of experience across B2B and B2C. I own SEO, SEM and content programs, analyze performance in Google Analytics, and run social and email campaigns. M.Sc. in Business Administration."),
    ("Diego", "Fernandez", "diego.fernandez@example.com", "+52 55 5555 0145", "Mexico City, Mexico", "Growth Marketer", "Rappi", 4,
     "B.A. Marketing, ITAM", "job_board",
     ["SEO", "Growth", "SEM", "Google Analytics", "Email Marketing", "Social Media"],
     "Growth marketer specializing in acquisition and experimentation.",
     "Growth marketer with 4 years of experience in acquisition and A/B testing. I run paid search and social campaigns, manage email funnels, and report with Google Analytics."),
    ("Hannah", "Larsen", "hannah.larsen@example.com", "+45 20 555 0112", "Copenhagen, Denmark", "Content Strategist", "Trustpilot", 5,
     "B.A. Journalism, University of Copenhagen", "referral",
     ["Content Marketing", "SEO", "Copywriting", "Social Media", "Google Analytics"],
     "Content strategist who turns brand stories into measurable traffic.",
     "Content strategist with 5 years of experience planning editorial calendars, writing SEO content, and growing organic traffic measured in Google Analytics."),
    ("Omar", "Farouk", "omar.farouk@example.com", "+971 50 555 0117", "Dubai, UAE", "Recruiter", "Careem", 4,
     "B.A. Psychology, American University of Beirut", "linkedin",
     ["Recruitment", "Sourcing", "Interviewing", "Onboarding", "ATS", "HRIS", "Employee Relations"],
     "Talent acquisition specialist with a people-first approach.",
     "Recruiter with 4 years of experience owning end-to-end hiring for engineering and GTM teams. I source through LinkedIn, run structured interviews, coordinate offers and onboarding, and work daily in an HRIS."),
    ("Grace", "Muriuki", "grace.muriuki@example.com", "+254 722 555 016", "Nairobi, Kenya", "HR Generalist", "Andela", 3,
     "B.A. Human Resource Management, University of Nairobi", "website",
     ["Recruitment", "Onboarding", "HRIS", "Employee Relations", "Compensation"],
     "HR generalist supporting the full employee lifecycle.",
     "HR generalist with 3 years of experience in recruitment, onboarding, employee relations and compensation support. Familiar with Workday and BambooHR."),
    ("Victor", "Novak", "victor.novak@example.com", "+420 603 555 015", "Prague, Czechia", "Financial Analyst", "Avast", 5,
     "M.Sc. Finance, Prague University of Economics", "job_board",
     ["Excel", "Financial Modeling", "Budgeting", "Reporting", "SQL", "Forecasting", "Tableau"],
     "Finance professional who builds models leadership trusts.",
     "Financial analyst with 5 years of experience in FP&A. I build financial models in Excel, own budgeting and forecasting cycles, and produce monthly reporting. I use SQL for data extraction and Tableau for dashboards."),
    ("Anita", "Sharma", "anita.sharma@example.com", "+91 99 555 0187", "New Delhi, India", "Finance Associate", "Paytm", 2,
     "B.Com (Hons), Shri Ram College of Commerce", "event",
     ["Excel", "Accounting", "Budgeting", "Reporting", "SQL"],
     "Detail-oriented finance professional early in her career.",
     "Finance associate with 2 years of experience in accounting and reporting. I maintain books in Excel and QuickBooks, support budgeting, and prepare monthly reports."),
    ("Ryan", "Carter", "ryan.carter@example.com", "+1 512 555 0190", "Austin, TX", "Account Executive", "HubSpot", 4,
     "B.A. Economics, University of Texas at Austin", "referral",
     ["SaaS Sales", "Lead Generation", "CRM", "Negotiation", "Account Management", "Salesforce", "Demos"],
     "Quota-crushing AE selling B2B SaaS into mid-market.",
     "Account executive with 4 years of B2B SaaS sales experience at HubSpot. I own the full cycle from lead generation to close, run demos, and manage pipeline in Salesforce. Consistently at 120%+ of quota."),
    ("Chloe", "Dubois", "chloe.dubois@example.com", "+33 1 55 55 0118", "Lyon, France", "Sales Development Rep", "Contentsquare", 2,
     "B.A. International Business, EM Lyon", "linkedin",
     ["Lead Generation", "CRM", "Prospecting", "Email Marketing"],
     "SDR with a gift for turning cold outreach into booked demos.",
     "Sales development representative with 2 years of experience in outbound prospecting. I build lists, write cold email sequences, and book demos for the AE team using CRM tools."),
    ("Liam", "Murphy", "liam.murphy@example.com", "+1 646 555 0121", "New York, NY", "Backend Engineer (Python)", "Spotify", 6,
     "B.S. Computer Science, NYU", "linkedin",
     ["Python", "Django", "PostgreSQL", "Docker", "AWS", "Celery", "Redis"],
     "Python backend engineer who has shipped at streaming scale.",
     "Backend engineer with 6 years of Python experience at Spotify. I have built services in Django and Flask, managed PostgreSQL and Redis at scale, and deployed with Docker on AWS."),
    ("Fatima", "Al-Sayed", "fatima.alsayed@example.com", "+966 55 555 0113", "Riyadh, Saudi Arabia", "Backend Developer", "STC Pay", 3,
     "B.S. Software Engineering, KFUPM", "agency",
     ["Python", "Django", "PostgreSQL", "Docker"],
     "Backend developer building fintech APIs in Python.",
     "Backend developer with 3 years of experience building fintech APIs with Python and Django. I write clean SQL against PostgreSQL and containerize services with Docker."),
    ("Oliver", "Smith", "oliver.smith@example.com", "+44 7911 555 016", "Manchester, UK", "Junior Developer", "Booking.com", 1,
     "B.Sc. Computer Science, University of Manchester", "job_board",
     ["Python", "JavaScript", "HTML/CSS", "SQL", "Git"],
     "Junior developer eager to grow in a strong engineering team.",
     "Junior developer with 1 year of experience. I write Python and JavaScript, know HTML/CSS and SQL, and use Git daily. I recently completed a bootcamp after my B.Sc. in Computer Science."),
    ("Zara", "Hussain", "zara.hussain@example.com", "+44 20 7946 0111", "London, UK", "Frontend Developer", "Revolut", 2,
     "B.S. Computer Science, Queen Mary University", "referral",
     ["JavaScript", "React", "TypeScript", "HTML/CSS", "Git"],
     "Frontend developer who loves building fast, accessible UIs.",
     "Frontend developer with 2 years of experience in React and TypeScript. I build accessible, high-performance interfaces and collaborate closely with designers."),
    ("Peter", "Kovac", "peter.kovac@example.com", "+421 905 555 017", "Bratislava, Slovakia", "QA Engineer", "ESET", 4,
     "B.E. Computer Science, Slovak University of Technology", "job_board",
     ["Python", "JavaScript", "SQL", "Docker", "Testing"],
     "QA engineer who automated himself out of manual testing.",
     "QA engineer with 4 years of experience. I write automated tests in Python and JavaScript, run CI pipelines, and know SQL and Docker well enough to debug in production."),
    ("Isabella", "Rossi", "isabella.rossi@example.com", "+39 333 555 0188", "Milan, Italy", "Product Manager", "Bending Spoons", 5,
     "M.B.A., Bocconi University", "website",
     ["Product Management", "Agile", "Jira", "User Research", "Data Analysis"],
     "Product manager shipping B2B products with tight feedback loops.",
     "Product manager with 5 years of experience. I write PRDs, run discovery with user research, and drive execution in Agile sprints with Jira. I use data analysis to prioritize."),
    ("Yuki", "Tanaka", "yuki.tanaka@example.com", "+81 90 5555 0144", "Tokyo, Japan", "DevOps Engineer", "Rakuten", 5,
     "B.S. Information Engineering, Waseda University", "linkedin",
     ["AWS", "Docker", "Kubernetes", "Terraform", "Linux", "Jenkins", "Grafana"],
     "DevOps engineer automating infrastructure for e-commerce at scale.",
     "DevOps engineer with 5 years of experience. I run AWS infrastructure with Terraform, operate Kubernetes, and maintain Jenkins CI/CD. I build dashboards in Grafana and Prometheus."),
    ("Amelia", "Wright", "amelia.wright@example.com", "+61 400 555 013", "Sydney, Australia", "Data Scientist", "Canva", 7,
     "Ph.D. Machine Learning, University of Sydney", "linkedin",
     ["Python", "Machine Learning", "Deep Learning", "TensorFlow", "NLP", "Pandas", "SQL", "Statistics"],
     "PhD-level data scientist applying deep learning to product problems.",
     "Data scientist with a Ph.D. in Machine Learning and 7 years of applied experience. I have built deep learning systems with TensorFlow, worked on NLP and computer vision, and run rigorous experiments."),
]

STATUS_POOL = [
    "new", "new", "new", "screening", "screening", "screening", "screening",
    "interview", "interview", "interview", "offer", "hired", "rejected", "rejected",
]


ACHIEVEMENT_POOL = [
    "Led delivery of a flagship initiative from discovery to launch",
    "Reduced operational costs by 18% through process automation",
    "Scaled the service to 2M+ monthly users with zero downtime",
    "Cut p95 latency by 40% by rearchitecting core data paths",
    "Mentored 4 junior teammates and ran weekly design reviews",
    "Shipped 20+ features across two major product cycles",
    "Drove a 23% lift in the team's key north-star metric",
    "Introduced a testing culture that lifted coverage from 35% to 82%",
    "Owned vendor selection and negotiation, saving $60k annually",
    "Coordinated cross-functional delivery across three squads",
    "Built internal tooling now used by 80+ engineers",
    "Presented quarterly roadmaps to leadership and stakeholders",
    "Onboarded 15+ hires and ran the team's hiring loop",
    "Resolved a long-standing data quality issue that blocked reporting",
]

NOTE_POOL = [
    "Strong culture-fit signal from the referral conversation.",
    "Called Tuesday morning — very responsive and enthusiastic.",
    "Asked about salary expectations; comfortable with the published range.",
    "Portfolio shows great attention to detail; requested a second look.",
    "Noticed a 6-month gap after 2023 — worth a gentle question in screening.",
    "Recruiter screen went well; recommended for the next stage.",
]


def _resume_text(c):
    first, last, email, phone, city, headline, company, years, edu, source, skills, summary, _ = c
    # Deterministic per-candidate variety
    idx = sum(ord(ch) for ch in first) % len(ACHIEVEMENT_POOL)
    a1 = ACHIEVEMENT_POOL[idx % len(ACHIEVEMENT_POOL)]
    a2 = ACHIEVEMENT_POOL[(idx + 3) % len(ACHIEVEMENT_POOL)]
    a3 = ACHIEVEMENT_POOL[(idx + 7) % len(ACHIEVEMENT_POOL)]
    if idx % 2 == 0:
        # Skills-first layout
        return f"""{first} {last}
{headline}
{email} · {phone} · {city} · linkedin.com/in/{first.lower()}-{last.lower()}

SUMMARY
{summary}

SKILLS
{", ".join(skills)}

EXPERIENCE
{company} — {headline}
2021 — Present
• {a1}
• {a2}
• {a3}

{company} — {headline}
2018 — 2021
• Owned delivery of key initiatives end-to-end
• Improved team velocity and code quality

EDUCATION
{edu}
"""
    # Experience-first layout
    return f"""{first} {last}
{headline}
{email} · {phone} · {city} · linkedin.com/in/{first.lower()}-{last.lower()}

SUMMARY
{summary}

EXPERIENCE
{company} — {headline}
2021 — Present
• {a3}
• {a1}
• Partnered with product, design and engineering stakeholders

{company} — {headline}
2018 — 2021
• {a2}
• Drove measurable improvements in quality and velocity

EDUCATION
{edu}

SKILLS
{", ".join(skills)}
"""


class Command(BaseCommand):
    help = "Seed the ATS with a realistic demo dataset."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Delete existing data first.")

    def handle(self, *args, **options):
        if options["flush"]:
            Interview.objects.all().delete()
            Application.objects.all().delete()
            Candidate.objects.all().delete()
            Job.objects.all().delete()
            self.stdout.write("Flushed existing recruitment data.")

        self._superuser()
        jobs = self._jobs()
        candidates = self._candidates()
        self._applications(jobs, candidates)
        self._interviews()
        self.stdout.write(self.style.SUCCESS(
            f"Seed complete — {len(jobs)} jobs, {len(candidates)} candidates, "
            f"candidates can be screened from any job page."
        ))

    def _superuser(self):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@ats.local", "admin12345")
            self.stdout.write("Created superuser: admin / admin12345")

    def _jobs(self):
        created = []
        for data in JOBS:
            job, _ = Job.objects.get_or_create(
                title=data["title"],
                defaults={
                    "department": data["department"],
                    "location": data["location"],
                    "employment_type": data["employment_type"],
                    "experience_level": data["experience_level"],
                    "min_salary": data["min_salary"],
                    "max_salary": data["max_salary"],
                    "status": data["status"],
                    "required_skills": data["required_skills"],
                    "nice_to_have_skills": data["nice_to_have_skills"],
                    "description": data["description"],
                    "responsibilities": data["responsibilities"],
                    "requirements": data["requirements"],
                },
            )
            created.append(job)
        return created

    def _candidates(self):
        created = []
        for c in CANDIDATES:
            first, last, email, phone, city, headline, company, years, edu, source, skills, summary, _ = c
            candidate, was_created = Candidate.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first, "last_name": last, "phone": phone,
                    "location": city, "headline": headline, "current_company": company,
                    "years_experience": years, "education": edu, "source": source,
                    "skills": skills, "summary": summary,
                },
            )
            if was_created:
                raw = _resume_text(c)
                resume = Resume(
                    candidate=candidate,
                    file_type="txt",
                    raw_text=raw,
                )
                resume.file.save(
                    f"{first.lower()}_{last.lower()}.txt",
                    ContentFile(raw.encode("utf-8")),
                    save=True,
                )
                from core.parsers import parse_resume
                resume.parsed = parse_resume(raw)
                resume.save(update_fields=["parsed", "updated_at"])
            created.append(candidate)
        return created

    def _applications(self, jobs, candidates):
        # Spread candidates across jobs so every job has applicants, biased so
        # stronger candidates land on jobs they fit.
        n = len(candidates)
        steps = (0, 3, 7, 11, 15, 19)  # together cover every candidate at least once
        for i, job in enumerate(jobs):
            for k, step in enumerate(steps):
                cand = candidates[(i + step) % n]
                status = STATUS_POOL[(i * len(steps) + k) % len(STATUS_POOL)]
                applied_at = timezone.now() - timedelta(days=(i * 3 + k) % 14, hours=(i + k) % 24)
                app, created = Application.objects.get_or_create(
                    job=job, candidate=cand,
                    defaults={"status": status, "resume": cand.resumes.first()},
                )
                if created:
                    Application.objects.filter(pk=app.pk).update(created_at=applied_at)

        from screening.engine import screen_job
        for job in jobs:
            screen_job(job, use_llm=False)

        # Seed a lived-in activity trail: apply events, stage moves, notes
        for i, app in enumerate(Application.objects.select_related("candidate", "job").all()):
            app.log_event(
                "apply",
                f"Applied to {app.job.title}",
            )
            if app.status != Application.Status.NEW:
                app.log_event(
                    "status",
                    f"Moved from New to {Application.Status(app.status).label} after initial review",
                )
            if i % 3 == 0:
                note = NOTE_POOL[i % len(NOTE_POOL)]
                app.log_event("note", note)
        self.stdout.write("Screened all seeded applications with the rule-based engine.")

    def _interviews(self):
        if Interview.objects.exists():
            return
        interviewable = list(
            Application.objects.filter(status__in=["interview", "offer"])
            .select_related("candidate", "job")
            .order_by("?")[:5]
        )
        for i, app in enumerate(interviewable[:3]):
            Interview.objects.create(
                application=app,
                scheduled_at=timezone.now() + timedelta(days=1 + i, hours=3 + i),
                duration_minutes=45,
                interview_type=random.choice(["video", "technical", "panel"]),
                interviewer=random.choice(["Sarah Chen", "David Okafor", "Lena Fischer"]),
                status="scheduled",
            )
        # Two completed interviews with feedback
        completed = list(Application.objects.filter(status__in=["interview", "offer"]).exclude(
            pk__in=[a.pk for a in interviewable[:3]]
        ).select_related("candidate", "job")[:2])
        for i, app in enumerate(completed):
            rating = random.choice([4, 5])
            Interview.objects.create(
                application=app,
                scheduled_at=timezone.now() - timedelta(days=3 + i),
                duration_minutes=60,
                interview_type="onsite",
                interviewer="Sarah Chen",
                status="completed",
                rating=rating,
                feedback=(
                    "Excellent technical depth and communication. Strong cultural fit — recommend moving forward."
                    if rating >= 4 else
                    "Solid fundamentals but limited experience with our stack."
                ),
            )
