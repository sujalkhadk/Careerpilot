import re
from jobspy import scrape_jobs


def clean_value(value, default="Not available"):
    if value is None:
        return default

    value = str(value).strip()

    if not value or value.lower() in ["nan", "none"]:
        return default

    return value


def get_jobs(career_goal, location="India"):

    job_list = []
    seen_urls = set()

    sites = ["google", "indeed", "naukri"]

    irrelevant_keywords = [
        "accountant",
        "accounting",
        "accounts assistant",
        "accounts manager",
        "office assistant",
        "performance marketing",
        "sales executive",
        "receptionist",
        "telecaller",
        "data entry"
    ]

    fresher_keywords = [
        "fresher",
        "freshers",
        "entry level",
        "entry-level",
        "junior",
        "intern",
        "internship",
        "trainee",
        "graduate",
        "associate developer"
    ]

    goal = (career_goal or "Software Developer").lower()

    # Match jobs to the selected career
    if any(word in goal for word in [
        "web", "frontend", "front-end"
    ]):
        relevant_keywords = [
            "web developer",
            "frontend",
            "front-end",
            "backend",
            "back-end",
            "full stack",
            "fullstack",
            "javascript",
            "react developer",
            "website developer",
            "software developer"
        ]

    elif "python" in goal:
        relevant_keywords = [
            "python",
            "software developer",
            "software engineer",
            "backend",
            "back-end",
            "django",
            "flask"
        ]

    elif "java" in goal:
        relevant_keywords = [
            "java developer",
            "software developer",
            "software engineer",
            "spring boot",
            "backend",
            "full stack"
        ]

    elif any(word in goal for word in [
        "data", "analyst", "machine learning"
    ]):
        relevant_keywords = [
            "data analyst",
            "data scientist",
            "business analyst",
            "sql",
            "power bi",
            "machine learning"
        ]

    else:
        relevant_keywords = [
            "software developer",
            "software engineer",
            "web developer",
            "python",
            "java",
            "programmer",
            "full stack"
        ]

    for site in sites:

        try:
            print(f"Trying job source: {site}")

            jobs = scrape_jobs(
                site_name=[site],
                search_term=career_goal,
                location=location,
                results_wanted=15,
                country_indeed="India",
                hours_old=72
            )

            if jobs is None or jobs.empty:
                print(f"No jobs found from {site}.")
                continue

            for _, job in jobs.iterrows():

                title = clean_value(job.get("title"), "Job")
                title_lower = title.lower()

                # Skip unrelated job categories
                if any(
                    word in title_lower
                    for word in irrelevant_keywords
                ):
                    continue

                # Keep roles relevant to the selected career
                if not any(
                    word in title_lower
                    for word in relevant_keywords
                ):
                    print("Skipping non-matching job:", title)
                    continue

                description = clean_value(
                    job.get("description"), ""
                ).lower()

                # Combine title and description to estimate experience
                experience_text = title_lower + " " + description

                is_fresher = any(
                    word in title_lower
                    for word in fresher_keywords
                )

                # Look for experience ranges, e.g. 1-2 years
                ranges = re.findall(
                    r"\b(\d{1,2})\s*(?:-|–|to)\s*"
                    r"(\d{1,2})\s*(?:years?|yrs?)\b",
                    experience_text
                )

                minimum_years = []

                for low, high in ranges:
                    minimum_years.append(int(low))

                # Look for requirements such as 2+ years
                plus_years = re.findall(
                    r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)\b",
                    experience_text
                )

                for years in plus_years:
                    minimum_years.append(int(years))

                # Look for explicit minimum requirements
                minimum_matches = re.findall(
                    r"\b(?:minimum|min\.?)\s*(\d{1,2})"
                    r"\s*(?:years?|yrs?)\b",
                    experience_text
                )

                for years in minimum_matches:
                    minimum_years.append(int(years))

                # Classify jobs without rejecting senior roles
                if is_fresher:
                    experience_level = "Fresher / Entry-level"
                    priority = 0

                elif minimum_years and min(minimum_years) <= 2:
                    experience_level = "0–2 years / Early career"
                    priority = 1

                elif not minimum_years:
                    experience_level = "Not specified"
                    priority = 2

                elif min(minimum_years) <= 3:
                    experience_level = "2–3 years / Experienced"
                    priority = 3

                else:
                    experience_level = "Senior / Experienced"
                    priority = 4

                company = clean_value(
                    job.get("company_name")
                )

                if company == "Not available":
                    company = clean_value(
                        job.get("company")
                    )

                job_location = clean_value(
                    job.get("location"),
                    location
                )

                job_url = clean_value(
                    job.get("job_url"),
                    ""
                )

                work_type = clean_value(
                    job.get("job_type")
                )

                # Keep only listings with usable links
                if not job_url.startswith("http"):
                    continue

                # Avoid duplicate jobs across sources
                if job_url in seen_urls:
                    continue

                seen_urls.add(job_url)

                job_list.append({
                    "title": title,
                    "company": company,
                    "location": job_location,
                    "url": job_url,
                    "work_type": work_type,
                    "fresher_friendly": priority <= 1,
                    "experience_level": experience_level,
                    "priority": priority
                })

        except Exception as e:
            print(f"{site} job scraping error: {e}")
            continue

    # Freshers first, early-career jobs next, senior roles last.
    # Senior jobs are retained rather than discarded.
    job_list.sort(
        key=lambda job: job["priority"]
    )

    # Remove the internal sorting field before returning results
    for job in job_list:
        job.pop("priority", None)

    print("Total relevant India jobs found:", len(job_list))

    return job_list[:10]