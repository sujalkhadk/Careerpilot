from flask import Flask, render_template, request
import pymupdf
import os
import re
import mysql.connector
from job_scraper import get_jobs
from werkzeug.utils import secure_filename
from google import genai
gemini_client = None

if os.environ.get("GEMINI_API_KEY"):
    gemini_client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

app = Flask(__name__)
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root1",
    database="careerpilot"
)

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
INTERVIEW_QUESTION_SOURCE = "Not generated yet"


def generate_ai_interview_questions(career_goal, skills, education, experience):
    global INTERVIEW_QUESTION_SOURCE

    goal = (career_goal or "").strip()
    skills = skills or ""
    education = education or ""
    experience = experience or ""

    fallback_questions = {
        "python": [
            "How would you use Python to solve a practical problem?",
            "What is the difference between a list and a tuple?",
            "How would you handle errors in a Python program?",
            "How would you debug incorrect program output?",
            "How would you explain a Python project you built?"
        ],
        "web": [
            "How do HTML, CSS, and JavaScript work together?",
            "How would you make a webpage responsive?",
            "How would you debug a webpage that looks incorrect?",
            "How would you explain a web project you built?",
            "How does a frontend communicate with a backend?"
        ],
        "java": [
            "What is the difference between a class and an object?",
            "What is inheritance in Java?",
            "What is the difference between overloading and overriding?",
            "How does exception handling work in Java?",
            "How can Java connect to a MySQL database?"
        ],
        "data": [
            "How would you handle missing values in a dataset?",
            "What is the purpose of SQL in data analysis?",
            "How would you visualize data clearly?",
            "How would you explain a data analysis project?",
            "How would you check whether your analysis is accurate?"
        ],
        "default": [
            "How would you solve an unfamiliar technical problem?",
            "What technical skill are you strongest in, and why?",
            "How would you explain a project you have worked on?",
            "How would you learn a new programming technology?",
            "How would you test whether your solution works?"
        ]
    }

    goal_lower = goal.lower()

    if "python" in goal_lower:
        fallback = fallback_questions["python"]
    elif any(word in goal_lower for word in [
        "web", "frontend", "front-end", "backend",
        "back-end", "full stack", "javascript"
    ]):
        fallback = fallback_questions["web"]
    elif "java" in goal_lower:
        fallback = fallback_questions["java"]
    elif any(word in goal_lower for word in [
        "data", "analyst", "machine learning", "ai"
    ]):
        fallback = fallback_questions["data"]
    else:
        fallback = fallback_questions["default"]

    if not gemini_client:
        INTERVIEW_QUESTION_SOURCE = "Fallback - Gemini not configured"
        print("Interview question source:", INTERVIEW_QUESTION_SOURCE)
        return fallback

    prompt = f"""
You are a technical interviewer preparing a college student for a job.

Career goal: {goal}
Skills: {skills}
Education: {education}
Experience: {experience}

Generate exactly 5 different interview questions personalized to this
student's career goal, skills, education, and experience.

Use appropriate technical questions and practical problem-solving scenarios.
Include project-related questions only when relevant.
Avoid generic questions and do not repeat questions.
Do not invent qualifications or work experience.
Return only the five questions, one per line, without numbering.
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config={"http_options": {"timeout": 10000}}
        )

        response_text = response.text or ""
        questions = []

        for line in response_text.splitlines():
            question = line.strip()
            question = re.sub(
                r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)",
                "",
                question
            )

            if question and question not in questions:
                questions.append(question)

        if len(questions) >= 5:
            INTERVIEW_QUESTION_SOURCE = "Gemini AI"
            print("Interview question source:", INTERVIEW_QUESTION_SOURCE)
            return questions[:5]

        print("Gemini returned fewer than five questions.")

    except Exception as e:
        print("Gemini interview questions unavailable:", e)

    INTERVIEW_QUESTION_SOURCE = "Fallback - Gemini request failed"
    print("Interview question source:", INTERVIEW_QUESTION_SOURCE)
    return fallback


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():

    name = request.form.get("name", "")
    email = request.form.get("email", "")
    phone = request.form.get("phone","").strip()
    education = request.form.get("education", "")
    skills = request.form.get("skills", "")
    career_goal = request.form.get("career_goal", "")
    experience = request.form.get("experience", "")
    projects = request.form.get("projects", "")
    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO students
        (name, email, education, skills, career_goal, experience)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (name, email, education, skills, career_goal, experience)
    )

    db.commit()
    cursor.close()

    resume_text = ""

    resume = request.files.get("resume")

    if resume and resume.filename:

        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            secure_filename(resume.filename)
        )

        resume.save(filepath)

        document = pymupdf.open(filepath)

        for page in document:
            resume_text += page.get_text()

        document.close()
    
    
    # Extract project details from the uploaded resume
    extracted_projects = ""

    if resume_text.strip():
        project_match = re.search(
            r"(?:ACADEMIC\s+AND\s+PERSONAL\s+PROJECTS|"
            r"ACADEMIC\s+PROJECTS|PERSONAL\s+PROJECTS|PROJECTS)"
            r"\s*(.*?)(?=\n\s*(?:EXPERIENCE|"
            r"INTERNSHIP|CERTIFICATIONS?|EDUCATION|"
            r"TECHNICAL\s+SKILLS|STRENGTHS|"
            r"ADDITIONAL\s+INFORMATION)\b|$)",
            resume_text,
            flags=re.IGNORECASE | re.DOTALL
        )

        if project_match:
            extracted_projects = project_match.group(1).strip()

            # Remove empty lines and excess whitespace
            extracted_projects = re.sub(
                r"\n\s*\n+", "\n", extracted_projects
            ).strip()

            # Avoid using obvious sample-resume placeholder content
            if re.search(
                r"sample resume for layout and practice|"
                r"replace bracketed fields",
                extracted_projects,
                flags=re.IGNORECASE
            ):
                extracted_projects = ""

    
    # Extract phone number from uploaded resume PDF
    resume_phone = ""

    if resume_text.strip():
        phone_match = re.search(
            r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)",
            resume_text
        )

        if phone_match:
            resume_phone = phone_match.group(0).strip()

    
    # Extract a section only when its heading appears on its own line
    def extract_pdf_section(start_heading, end_headings):
        if not resume_text.strip():
            return ""

        pattern = (
            r"(?im)^[ \t]*(?:"
            + start_heading
            + r")[ \t]*:?[ \t]*\r?\n"
            + r"(.*?)"
            + r"(?=^[ \t]*(?:"
            + end_headings
            + r")\b|\Z)"
        )

        match = re.search(
            pattern,
            resume_text,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
        )

        if match:
            return re.sub(
                r"\n\s*\n+",
                "\n",
                match.group(1)
            ).strip()

        return ""


    extracted_education = extract_pdf_section(
        r"\bEDUCATION\b",
        r"TECHNICAL\s+SKILLS|ACADEMIC\s+PROJECTS|"
        r"ACADEMIC\s+AND\s+PERSONAL\s+PROJECTS|EXPERIENCE"
    )

    extracted_skills = extract_pdf_section(
        r"TECHNICAL\s+SKILLS",
        r"ACADEMIC\s+PROJECTS|ACADEMIC\s+AND\s+PERSONAL\s+PROJECTS|"
        r"EXPERIENCE|CERTIFICATIONS?"
    )

    
    
    extracted_experience = extract_pdf_section(
        r"(?:WORK\s+EXPERIENCE|PROFESSIONAL\s+EXPERIENCE|EXPERIENCE|INTERNSHIPS?)",
        r"EDUCATION|TECHNICAL\s+SKILLS|"
        r"ACADEMIC\s*/?\s*PRACTICE\s+PROJECTS|"
        r"ACADEMIC\s+AND\s+PERSONAL\s+PROJECTS|"
        r"ACADEMIC\s+PROJECTS|PERSONAL\s+PROJECTS|PROJECTS|"
        r"CERTIFICATIONS?|STRENGTHS|ADDITIONAL\s+INFORMATION|LANGUAGES"
    )



    
    skills_lower = skills.lower()
    goal_lower = career_goal.lower()
    resume_warnings = []

    if resume_text.strip():
        resume_lower = resume_text.lower()

        normalized_resume = re.sub(
            r"[^a-z0-9]+", " ", resume_lower
        ).strip()

        # 1. Check profile name
        if name.strip():
            profile_name = re.sub(
                r"[^a-z0-9]+", " ", name.lower()
            ).strip()

            resume_header = " ".join(resume_lower.split()[:20])
            normalized_header = re.sub(
                r"[^a-z0-9]+", " ", resume_header
            ).strip()

            if profile_name and profile_name not in normalized_header:
                resume_warnings.append(
                    "The profile name was not found near the beginning "
                    "of the uploaded resume."
                )

        # 2. Check profile email
        if email.strip():
            resume_emails = re.findall(
                r"[\w\.-]+@[\w\.-]+\.\w+", resume_text
            )

            if not any(
                email.strip().lower() == found.lower()
                for found in resume_emails
            ):
                resume_warnings.append(
                    "The profile email was not found in the uploaded resume."
                )

        # 3. Check education
        if education.strip():
            normalized_education = re.sub(
                r"[^a-z0-9]+", " ", education.lower()
            ).strip()

            if (
                normalized_education
                and normalized_education not in normalized_resume
            ):
                resume_warnings.append(
                    "The profile education was not found in the uploaded resume."
                )

        # 4. Check skills
        if skills.strip():
            profile_skills = [
                skill.strip()
                for skill in re.split(r"[,;\n|]+", skills)
                if skill.strip()
            ]

            missing_skills = []

            for skill in profile_skills:
                skill_pattern = (
                    r"(?<![a-z0-9])"
                    + re.escape(skill.lower())
                    + r"(?![a-z0-9])"
                )

                if not re.search(skill_pattern, resume_lower):
                    missing_skills.append(skill)

            if missing_skills:
                resume_warnings.append(
                    "These profile skills were not found in the uploaded "
                    "resume: " + ", ".join(missing_skills)
                    + ". Check whether they should be added."
                )
    recommendations = []

    if "python" in skills_lower:
        recommendations.append("Python Developer")

    if "java" in skills_lower:
        recommendations.append("Java Developer")

    if "html" in skills_lower and "css" in skills_lower:
        recommendations.append("Web Developer")
        recommendations.append("Frontend Developer")

    if "javascript" in skills_lower:
        recommendations.append("JavaScript Developer")

    if "mysql" in skills_lower or "sql" in skills_lower:
        recommendations.append("Backend Developer")
        recommendations.append("Database Developer")

    if "machine learning" in skills_lower or "ml" in skills_lower:
        recommendations.append("Machine Learning Engineer")

    if "pandas" in skills_lower:
        recommendations.append("Data Analyst")

    if "python" in skills_lower and (
        "pandas" in skills_lower or "data" in skills_lower
    ):
        recommendations.append("Data Scientist")

    if "git" in skills_lower:
        recommendations.append("Software Developer")

    if not recommendations:
        recommendations.append("Software Developer")

    career_skills = {

    "python": [
        "python", "git", "sql", "mysql", "flask", "django", "api"
    ],

    "java": [
        "java", "spring", "jdbc", "sql", "mysql", "git", "api", "oop"
    ],

    "web": [
        "html", "css", "javascript", "react", "api", "mysql",
        "git", "responsive"
    ],

    "frontend": [
        "html", "css", "javascript", "react", "bootstrap",
        "responsive", "git", "ui"
    ],

    "backend": [
        "python", "java", "flask", "django", "sql",
        "mysql", "api", "git"
    ],

    "full stack": [
        "html", "css", "javascript", "react", "node",
        "python", "sql", "mysql", "api", "git"
    ],

    "javascript": [
        "javascript", "html", "css", "react", "node",
        "api", "git"
    ],

    "react": [
        "javascript", "html", "css", "react",
        "redux", "api", "git"
    ],

    "node": [
        "javascript", "node", "express", "api",
        "mongodb", "sql", "git"
    ],

    "software": [
        "python", "java", "javascript", "sql",
        "git", "github", "oop", "api"
    ],

    "mobile": [
        "java", "kotlin", "flutter", "dart",
        "android", "firebase", "git"
    ],

    "game": [
        "c++", "c#", "unity", "unreal",
        "game development", "git"
    ],

    "data analyst": [
        "python", "sql", "mysql", "excel", "pandas",
        "power bi", "tableau", "data analysis"
    ],

    "data scientist": [
        "python", "pandas", "numpy", "sql",
        "machine learning", "statistics",
        "scikit-learn", "data analysis"
    ],

    "data engineer": [
        "python", "sql", "mysql", "etl",
        "spark", "hadoop", "data pipeline", "git"
    ],

    "machine learning": [
        "python", "pandas", "numpy",
        "machine learning", "scikit-learn",
        "tensorflow", "statistics", "model"
    ],

    "ai": [
        "python", "machine learning", "deep learning",
        "tensorflow", "pytorch", "numpy", "pandas"
    ],

    "nlp": [
        "python", "nlp", "natural language processing",
        "machine learning", "pandas", "numpy",
        "transformers"
    ],

    "business intelligence": [
        "sql", "excel", "power bi",
        "tableau", "data analysis", "dashboard"
    ],

    "cloud": [
        "aws", "azure", "google cloud",
        "linux", "docker", "kubernetes", "git"
    ],

    "devops": [
        "linux", "docker", "kubernetes",
        "jenkins", "git", "aws", "ci/cd"
    ],

    "site reliability": [
        "linux", "docker", "kubernetes",
        "monitoring", "aws", "python", "git"
    ],

    "cybersecurity": [
        "networking", "linux", "cybersecurity",
        "firewall", "siem", "python", "security"
    ],

    "soc": [
        "networking", "linux", "siem",
        "incident response", "cybersecurity",
        "firewall", "security"
    ],

    "security": [
        "networking", "linux", "cybersecurity",
        "firewall", "siem", "python", "security"
    ],

    "ethical hacker": [
        "networking", "linux", "python",
        "penetration testing", "kali linux",
        "burp suite", "cybersecurity"
    ],

    "penetration tester": [
        "networking", "linux", "python",
        "penetration testing", "kali linux",
        "burp suite", "cybersecurity"
    ],

    "database": [
        "sql", "mysql", "postgresql",
        "mongodb", "database", "dbms",
        "python", "java"
    ],

    "dba": [
        "sql", "mysql", "postgresql",
        "database", "dbms", "backup",
        "database administration"
    ],

    "system administrator": [
        "linux", "windows server",
        "networking", "system administration",
        "powershell", "security"
    ],

    "it support": [
        "windows", "linux", "networking",
        "hardware", "troubleshooting",
        "technical support"
    ],

    "qa": [
        "testing", "manual testing",
        "selenium", "java", "python",
        "sql", "git"
    ],

    "software tester": [
        "testing", "manual testing",
        "selenium", "sql", "java",
        "python", "git"
    ],

    "automation tester": [
        "selenium", "testing", "java",
        "python", "automation", "sql", "git"
    ],

    "ui/ux": [
        "figma", "ui", "ux", "wireframe",
        "prototyping", "user research"
    ],

    "business analyst": [
        "sql", "excel", "business analysis",
        "requirements", "data analysis",
        "power bi", "communication"
    ],

    "it consultant": [
        "sql", "python", "java",
        "cloud", "networking",
        "business analysis", "communication"
    ],

    "technical consultant": [
        "python", "java", "sql",
        "cloud", "networking",
        "troubleshooting", "communication"
    ]
}

    profile_text = skills_lower
    resume_lower_for_match = resume_text.lower() if resume_text else ""

    combined_skills = profile_text + " " + resume_lower_for_match

    if "python" in goal_lower:
        selected_career = "python"

    elif "java" in goal_lower:
        selected_career = "java"

    elif "full stack" in goal_lower:
        selected_career = "full stack"

    elif "react" in goal_lower:
        selected_career = "react"

    elif "node" in goal_lower:
        selected_career = "node"

    elif "javascript" in goal_lower:
        selected_career = "javascript"

    elif "frontend" in goal_lower:
        selected_career = "frontend"

    elif "backend" in goal_lower:
        selected_career = "backend"

    elif "web" in goal_lower:
        selected_career = "web"

    elif "mobile" in goal_lower:
        selected_career = "mobile"

    elif "game" in goal_lower:
        selected_career = "game"

    elif "data analyst" in goal_lower:
        selected_career = "data analyst"

    elif "data scientist" in goal_lower:
        selected_career = "data scientist"

    elif "data engineer" in goal_lower:
        selected_career = "data engineer"

    elif "machine learning" in goal_lower:
        selected_career = "machine learning"

    elif "ai engineer" in goal_lower:
        selected_career = "ai"

    elif "nlp" in goal_lower:
        selected_career = "nlp"

    elif "business intelligence" in goal_lower:
        selected_career = "business intelligence"

    elif "cloud" in goal_lower:
        selected_career = "cloud"

    elif "devops" in goal_lower:
        selected_career = "devops"

    elif "site reliability" in goal_lower:
        selected_career = "site reliability"

    elif "cybersecurity" in goal_lower:
        selected_career = "cybersecurity"

    elif "soc" in goal_lower:
        selected_career = "soc"

    elif "security engineer" in goal_lower:
        selected_career = "security"

    elif "ethical hacker" in goal_lower:
        selected_career = "ethical hacker"

    elif "penetration" in goal_lower:
        selected_career = "penetration tester"

    elif "database administrator" in goal_lower:
        selected_career = "dba"

    elif "database" in goal_lower:
        selected_career = "database"

    elif "system administrator" in goal_lower:
        selected_career = "system administrator"

    elif "it support" in goal_lower:
        selected_career = "it support"

    elif "automation tester" in goal_lower:
        selected_career = "automation tester"

    elif "software tester" in goal_lower:
        selected_career = "software tester"

    elif "qa" in goal_lower:
        selected_career = "qa"

    elif "ui/ux" in goal_lower:
        selected_career = "ui/ux"

    elif "business analyst" in goal_lower:
        selected_career = "business analyst"

    elif "technical consultant" in goal_lower:
        selected_career = "technical consultant"

    elif "it consultant" in goal_lower:
        selected_career = "it consultant"

    else:
        selected_career = "software"

    
    required_skills = career_skills[selected_career]
    career_match_required_skills = required_skills.copy()

    skill_gaps = []
    profile_skills_lower = skills_lower.lower()
    resume_skills_lower = resume_text.lower()

    combined_skill_text = profile_skills_lower + " " + resume_skills_lower
    combined_skills = combined_skill_text

    career_skill_gaps = {
        "web": ["JavaScript", "Git and GitHub", "React", "REST APIs", "Responsive Design"],
        "frontend": ["JavaScript", "Git and GitHub", "React", "Bootstrap", "Responsive Design"],
        "backend": ["Python", "Git and GitHub", "REST APIs", "Flask or Django", "SQL"],
        "python": ["Git and GitHub", "Flask or Django", "REST APIs", "SQL", "Testing"],
        "java": ["Git and GitHub", "Spring", "JDBC", "REST APIs", "SQL"],
        "data analyst": ["Excel", "SQL", "Pandas", "Power BI", "Data Visualization"],
        "data scientist": ["Pandas", "NumPy", "Machine Learning", "Statistics", "Scikit-learn"],
        "machine learning": ["Python", "Pandas", "NumPy", "Scikit-learn", "Statistics"]
    }

    if "data scientist" in goal_lower:
        required_skills = career_skill_gaps["data scientist"]
    elif "data analyst" in goal_lower:
        required_skills = career_skill_gaps["data analyst"]
    elif "machine learning" in goal_lower or "ml" in goal_lower:
        required_skills = career_skill_gaps["machine learning"]
    elif "frontend" in goal_lower:
        required_skills = career_skill_gaps["frontend"]
    elif "backend" in goal_lower:
        required_skills = career_skill_gaps["backend"]
    elif "web" in goal_lower:
        required_skills = career_skill_gaps["web"]
    elif "python" in goal_lower:
        required_skills = career_skill_gaps["python"]
    elif "java" in goal_lower:
        required_skills = career_skill_gaps["java"]
    else:
        required_skills = ["Python", "SQL", "Git and GitHub", "JavaScript"]

    # Calculate Career Match using the full career skill list
    matched_skills = []

    for skill in career_match_required_skills:
        skill_key = skill.lower()

        if skill_key in profile_skills_lower or skill_key in resume_skills_lower:
            matched_skills.append(skill)

    career_score = round(
        (len(matched_skills) / len(career_match_required_skills)) * 100
    ) if career_match_required_skills else 0

    # Calculate the skills the user should learn
    for skill in required_skills:
        skill_key = skill.lower()

        if "flask or django" in skill_key:
            if "flask" not in combined_skills and "django" not in combined_skills:
                skill_gaps.append(skill)
        elif "git and github" in skill_key:
            if "git" not in combined_skills and "github" not in combined_skills:
                skill_gaps.append(skill)
        elif "rest apis" in skill_key:
            if "api" not in combined_skills and "rest" not in combined_skills:
                skill_gaps.append(skill)
        elif skill_key not in combined_skills:
            skill_gaps.append(skill)
    
    print("DEBUG: Resume text length:", len(resume_text))
    print("DEBUG: Resume text preview:", resume_text[:200])

    ats_score = 0
    ats_suggestions = []

    if resume_text.strip():
        resume_lower = resume_text.lower()

        # Check whether profile details match the uploaded resume
        normalized_resume = " ".join(resume_lower.split())

        if name.strip() and " ".join(name.lower().split()) not in normalized_resume:
            resume_warnings.append(
                "The profile name was not found in the uploaded resume. "
                "Please check whether the details match."
            )

        if email.strip() and email.strip().lower() not in normalized_resume:
            resume_warnings.append(
                "The profile email was not found in the uploaded resume. "
                "Please check whether the details match."
            )

        base_checks = {
            "education": "education" in resume_lower,
            "skills": "skills" in resume_lower,
            "projects": "projects" in resume_lower,
            "experience": "experience" in resume_lower,
            "email": bool(re.search(
                r'[\w\.-]+@[\w\.-]+\.\w+',
                resume_text
            )),
            "phone": bool(re.search(
                r'(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)',
                resume_text
            )),
            "github": "github.com" in resume_lower,
            "linkedin": "linkedin.com" in resume_lower
        }

        check_weights = {
            "education": 6,
            "skills": 6,
            "projects": 6,
            "experience": 6,
            "email": 10,
            "phone": 10,
            "github": 5,
            "linkedin": 5
        }

        for check_name, check_passed in base_checks.items():
            if check_passed:
                ats_score += check_weights[check_name]

        if "career objective" in resume_lower or "summary" in resume_lower:
            ats_score += 10
        else:
            ats_suggestions.append(
                "Add a clear career objective or professional summary."
            )

        if "web" in goal_lower:
            selected_keywords = [
                "html", "css", "javascript", "react",
                "api", "mysql", "git", "github"
            ]
        elif "frontend" in goal_lower:
            selected_keywords = [
                "html", "css", "javascript", "react",
                "bootstrap", "responsive", "git", "github"
            ]
        elif "backend" in goal_lower:
            selected_keywords = [
                "python", "java", "flask", "django",
                "api", "mysql", "sql", "git"
            ]
        elif "python" in goal_lower:
            selected_keywords = [
                "python", "flask", "django", "pandas",
                "numpy", "sql", "api", "git"
            ]
        elif "java" in goal_lower:
            selected_keywords = [
                "java", "spring", "jdbc", "sql",
                "oop", "mysql", "api", "git"
            ]
        else:
            selected_keywords = [
                "python", "java", "sql",
                "html", "css", "javascript"
            ]

        keyword_matches = sum(
            1 for keyword in selected_keywords
            if keyword in resume_lower
        )

        if selected_keywords:
            keyword_score = round(
                (keyword_matches / len(selected_keywords)) * 36
            )
            ats_score += keyword_score

        section_suggestions = {
            "education": "Add an Education section.",
            "skills": "Add a Skills section.",
            "projects": "Add a Projects section.",
            "experience": (
                "Add an Experience section, internship, "
                "or relevant practical experience."
            )
        }

        for section, suggestion in section_suggestions.items():
            if not base_checks[section]:
                ats_suggestions.append(suggestion)

        if not base_checks["email"]:
            ats_suggestions.append("Add a valid email address.")

        if not base_checks["phone"]:
            ats_suggestions.append("Add a valid phone number.")

        if not base_checks["github"]:
            ats_suggestions.append("Add your GitHub profile.")

        if not base_checks["linkedin"]:
            ats_suggestions.append("Add your LinkedIn profile.")

        if keyword_matches < 3:
            ats_suggestions.append(
                f"Add more skills related to {career_goal}."
            )

        
        # Resume quality checks
        quality_warnings = []

        # 1. Detect unfinished placeholders
        placeholder_patterns = [
            r"\[[^\]]+\]",
            r"your name",
            r"your email",
            r"lorem ipsum",
            r"replace this",
            r"insert here"
        ]

        for pattern in placeholder_patterns:
            if re.search(pattern, resume_lower, re.IGNORECASE):
                quality_warnings.append(
                    "Your resume contains unfinished placeholders. "
                    "Replace text such as [College Name] or "
                    "[CGPA / Percentage] with your actual details."
                )
                break

        # 2. Check project detail
        project_section = ""
        project_match = re.search(
            r"academic projects(.*?)(?:experience|certifications|strengths|$)",
            resume_lower,
            re.DOTALL
        )

        if project_match:
            project_section = project_match.group(1).strip()

        if not project_section:
            quality_warnings.append(
                "Add an Academic Projects section with project names "
                "and descriptions."
            )
        elif len(project_section.split()) < 25:
            quality_warnings.append(
                "Add more details to your projects, including what you "
                "built, which technologies you used, and what you did."
            )

        # 3. Check certification placeholders
        if (
            "certifications" in resume_lower
            and re.search(r"\[[^\]]+\]", resume_lower)
        ):
            quality_warnings.append(
                "Complete or remove unfinished certification details."
            )

        # 4. Avoid presenting a high score as proof of accuracy
        ats_score = min(ats_score, 100)

        if quality_warnings:
            ats_suggestions.extend(quality_warnings)

        if quality_warnings:
            ats_score = max(0, ats_score - 15)

            ats_suggestions.append(
                "Your resume has a good basic structure, but complete "
                "the quality issues above before applying."
            )

    else:
        ats_score = 0
        ats_suggestions = [
            "Upload a PDF resume to receive an ATS analysis."
        ]
    # Generate interview questions using Gemini or fallback questions
    interview_questions = generate_ai_interview_questions(
        career_goal,
        skills,
        education,
        experience
    )

    # Generate Career Objective
    career_objective = (
        f"Motivated student pursuing {education}, "
        f"seeking an opportunity as a {career_goal} "
        f"to apply technical skills in {skills} "
        f"and contribute to real-world projects."
    )

    
    
    
    # Choose the information for the generated resume

    profile_projects = projects.strip()
    profile_experience = experience.strip()

    # Prefer PDF details, falling back to profile details
    resume_education = extracted_education or education.strip()

    # Avoid using obvious education placeholders from sample resumes
    if re.search(
        r"Degree\s*/\s*Diploma|College name:\s*Add|"
        r"Expected graduation:\s*Add",
        resume_education,
        flags=re.IGNORECASE
    ):
        resume_education = education.strip() or resume_education

    resume_skills = extracted_skills or skills.strip()

    # Use extracted work experience only when a real section exists
    if extracted_experience:
        resume_experience = extracted_experience
    elif profile_experience.lower() not in [
        "", "0-1 year", "fresher", "no experience", "none"
    ]:
        resume_experience = profile_experience
    else:
        resume_experience = (
            "Fresher seeking opportunities to gain practical "
            "industry experience."
        )

    # Prefer projects from the uploaded PDF
    resume_projects = extracted_projects or profile_projects or (
        "Add your academic or personal projects, "
        "including technologies used and your contribution."
    )

    # Generate the complete resume text
    resume_draft = f"""
{name}

Email: {email}
Phone: {resume_phone}

PROFESSIONAL SUMMARY
{career_objective}

EDUCATION
{resume_education}

TECHNICAL SKILLS
{resume_skills}

ACADEMIC AND PERSONAL PROJECTS
{resume_projects}

EXPERIENCE
{resume_experience}

CAREER GOAL
{career_goal}

Review all details and remove any placeholders before applying.
"""



    return render_template(
        "result.html",
        name=name,
        email=email,
        resume_warnings=resume_warnings,
        education=education,
        career_objective=career_objective,
        resume_draft=resume_draft,
        skills=skills,
        career_goal=career_goal,
        experience=experience,
        projects=projects,
        resume_projects=resume_projects,
        resume_education=resume_education,
        resume_skills=resume_skills,
        resume_phone=resume_phone,
        resume_experience=resume_experience,
        resume_text=resume_text,
        recommendations=recommendations,
        skill_gaps=skill_gaps,
        career_score=career_score,
        ats_score=ats_score,
        ats_suggestions=ats_suggestions,
        interview_questions=interview_questions,
        interview_question_source=INTERVIEW_QUESTION_SOURCE
    )

@app.route("/jobs")
def jobs():

    career_goal = request.args.get(
        "career_goal",
        "Software Developer"
    )

    jobs = get_jobs(career_goal,"India")

    return render_template(
        "jobs.html",
        career_goal=career_goal,
        jobs=jobs
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )