"""
SKILLS_TAXONOMY — a lightweight skill dictionary used for resume parsing and
rule-based screening. Keys are canonical skill names; values are lists of
aliases / sub-strings that may appear in resumes or job descriptions.

The screening engine treats a resume as matching a skill when any alias
appears as a token (or token-prefix, e.g. "python" matches "python3") in the
normalized resume text.
"""

SKILLS_TAXONOMY = {
    # --- Programming languages ---
    "python": ["python", "python3", "django rest"],
    "java": ["java", "j2ee", "spring boot"],
    "javascript": ["javascript", "js/es6", "ecmascript"],
    "typescript": ["typescript"],
    "c++": ["c++", "cpp"],
    "c": ["c programming", "ansi c"],
    "c#": ["c#", "c sharp", ".net"],
    "go": ["golang", "go programming"],
    "rust": ["rust"],
    "ruby": ["ruby", "rails"],
    "php": ["php", "laravel"],
    "swift": ["swift"],
    "kotlin": ["kotlin", "android development"],
    "sql": ["sql", "mysql", "postgresql", "postgres", "sqlite", "pl/sql"],
    "r": ["r programming", "tidyverse"],
    "scala": ["scala", "spark"],
    "html/css": ["html", "css", "sass", "scss", "tailwind css", "bootstrap"],
    "bash": ["bash", "shell scripting", "shell script", "zsh"],
    "powershell": ["powershell"],

    # --- Frameworks & libraries ---
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "react": ["react", "react.js", "reactjs"],
    "angular": ["angular", "angularjs"],
    "vue": ["vue.js", "vuejs", "nuxt"],
    "svelte": ["svelte", "sveltekit"],
    "next.js": ["next.js", "nextjs"],
    "node.js": ["node.js", "nodejs", "node"],
    "express": ["express.js", "expressjs"],
    "spring": ["spring", "spring boot", "hibernate"],
    "asp.net": ["asp.net", ".net core"],
    "jquery": ["jquery"],
    "tailwind": ["tailwind"],
    "pandas": ["pandas"],
    "numpy": ["numpy", "scipy"],
    "matplotlib": ["matplotlib", "seaborn"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "tensorflow": ["tensorflow", "tf"],
    "pytorch": ["pytorch"],
    "keras": ["keras"],
    "opencv": ["opencv"],
    "selenium": ["selenium"],
    "playwright": ["playwright"],
    "celery": ["celery", "rabbitmq"],
    "kafka": ["kafka", "apache kafka"],
    "graphql": ["graphql", "apollo"],
    "rest api": ["rest api", "restful", "rest apis"],

    # --- Databases & data stores ---
    "postgresql": ["postgresql", "postgres"],
    "mysql": ["mysql"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "elastic"],
    "dynamodb": ["dynamodb"],
    "oracle": ["oracle"],
    "sql server": ["sql server", "mssql"],
    "cassandra": ["cassandra"],
    "snowflake": ["snowflake"],
    "bigquery": ["bigquery"],
    "airflow": ["airflow", "apache airflow"],
    "dbt": ["dbt", "data build tool"],

    # --- Cloud & DevOps ---
    "aws": ["aws", "amazon web services", "s3", "ec2", "lambda"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"],
    "ansible": ["ansible"],
    "jenkins": ["jenkins", "ci/cd pipeline", "cicd"],
    "github actions": ["github actions", "gh actions"],
    "gitlab ci": ["gitlab ci"],
    "git": ["git", "github", "gitlab", "bitbucket"],
    "linux": ["linux", "unix"],
    "nginx": ["nginx"],
    "prometheus": ["prometheus"],
    "grafana": ["grafana"],
    "serverless": ["serverless"],
    "microservices": ["microservices", "micro service"],
    "system design": ["system design", "distributed systems", "scalable architecture"],

    # --- Data science & AI ---
    "machine learning": ["machine learning", "ml models", "mlops"],
    "deep learning": ["deep learning", "neural network", "cnn", "rnn", "transformer"],
    "nlp": ["nlp", "natural language processing", "nltk", "spacy"],
    "llm": ["llm", "large language model", "gpt", "langchain", "rag", "prompt engineering"],
    "computer vision": ["computer vision", "image recognition", "object detection"],
    "data analysis": ["data analysis", "data analytics", "exploratory data analysis"],
    "etl": ["etl", "data pipelines", "data pipeline", "data warehousing"],
    "tableau": ["tableau"],
    "power bi": ["power bi", "powerbi"],
    "looker": ["looker"],
    "excel": ["excel", "spreadsheet", "vba"],
    "statistics": ["statistics", "statistical", "hypothesis testing"],
    "experimentation": ["experimentation", "a/b testing", "ab testing"],

    # --- Design & product ---
    "figma": ["figma"],
    "sketch": ["sketch"],
    "adobe xd": ["adobe xd"],
    "photoshop": ["photoshop"],
    "illustrator": ["illustrator"],
    "ui/ux": ["ui/ux", "user interface", "user experience", "ux research", "uxr"],
    "wireframing": ["wireframe", "wireframing", "prototyping", "prototype", "mockup"],
    "design systems": ["design system", "component library"],
    "accessibility": ["accessibility", "wcag", "a11y"],
    "user research": ["user research", "usability testing", "user testing", "interviews with users"],
    "product management": ["product management", "product roadmap", "product strategy", "prd"],
    "agile": ["agile", "scrum", "kanban", "sprint"],
    "jira": ["jira", "confluence"],
    "figjam": ["figjam", "mural", "miro"],

    # --- Marketing & growth ---
    "seo": ["seo", "search engine optimization", "google search console"],
    "sem": ["sem", "google ads", "ppc", "paid search", "adwords"],
    "content marketing": ["content marketing", "content strategy", "copywriting", "blog writing"],
    "social media": ["social media", "instagram marketing", "linkedin marketing", "tiktok"],
    "email marketing": ["email marketing", "mailchimp", "klaviyo"],
    "google analytics": ["google analytics", "ga4", "analytics"],
    "crm": ["crm", "hubspot crm", "zoho crm", "pipedrive", "freshsales"],
    "marketing automation": ["marketing automation", "marketo", "pardot"],
    "growth hacking": ["growth hacking", "growth marketing"],
    "branding": ["branding", "brand strategy", "positioning"],
    "public relations": ["public relations", "pr", "press release", "media relations"],
    "market research": ["market research", "competitor analysis", "customer research"],

    # --- Sales ---
    "sales": ["sales", "b2b sales", "closing", "cold calling"],
    "saas sales": ["saas sales", "saas", "software sales"],
    "account management": ["account management", "key accounts", "customer success"],
    "negotiation": ["negotiation", "deal negotiation", "closing deals"],
    "salesforce crm": ["salesforce", "salesforce crm", "sfdc"],
    "lead generation": ["lead generation", "lead gen", "prospecting", "outbound"],
    "demos": ["product demo", "demos", "sales demos", "poc"],

    # --- HR & people ---
    "recruitment": ["recruitment", "talent acquisition", "sourcing", "hiring"],
    "onboarding": ["onboarding", "new hire"],
    "performance management": ["performance management", "performance review", "okr", "kpi"],
    "employee engagement": ["employee engagement", "retention", "culture"],
    "compensation": ["compensation", "salary benchmarking", "benefits", "payroll"],
    "hr compliance": ["compliance", "labor law", "employment law", "equal opportunity"],
    "hr information systems": ["hrms", "workday", "bamboo", "sap successfactors", "greenhouse"],
    "interviewing": ["interviewing", "behavioral interviews", "structured interviews", "hiring manager"],
    "employee relations": ["employee relations", "grievance", "disciplinary"],

    # --- Finance & operations ---
    "financial modeling": ["financial modeling", "financial model", "valuation", "dcf"],
    "budgeting": ["budgeting", "budget", "forecasting", "forecast"],
    "accounting": ["accounting", "bookkeeping", "gaap", "ifrs", "quickbooks", "xero"],
    "audit": ["audit", "internal audit", "sox"],
    "reporting": ["financial reporting", "management reporting", "monthly close", "reconciliation"],
    "sql finance": ["sql finance", "data extraction"],
    "erp": ["erp", "sap", "netsuite", "oracle financials"],
    "process improvement": ["process improvement", "lean", "six sigma", "continuous improvement"],
    "project management": ["project management", "pmp", "prince2", "project planning", "stakeholder management"],
    "operations": ["operations", "operational", "supply chain", "logistics", "procurement"],

    # --- Soft skills / general ---
    "communication": ["communication", "presentation", "public speaking", "storytelling"],
    "leadership": ["leadership", "team lead", "mentoring", "coaching", "managing"],
    "teamwork": ["teamwork", "collaboration", "cross-functional", "cross functional"],
    "problem solving": ["problem solving", "analytical", "critical thinking", "troubleshooting"],
    "time management": ["time management", "prioritization", "deadline"],
    "adaptability": ["adaptability", "fast-paced", "learning agility"],
    "attention to detail": ["attention to detail", "detail-oriented", "detail oriented"],
    "decision making": ["decision making", "data-driven", "data driven", "strategic thinking"],
}


def build_search_index():
    """
    Return a dict mapping lowercase alias -> canonical skill name.
    Used by the parser and the screening engine for O(1) lookups.
    """
    index = {}
    for canonical, aliases in SKILLS_TAXONOMY.items():
        for alias in aliases:
            index[alias.strip().lower()] = canonical
    return index


SKILL_INDEX = build_search_index()

# Multi-word aliases are matched only when they appear as full phrases.
# Single-word aliases are matched as whole tokens (or token prefixes).
def _alias_tokens(alias):
    return alias.split()
