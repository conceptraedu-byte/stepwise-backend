def socratic_reply(user_text: str) -> str:
    text = user_text.lower()

    # ---------- STAGE 0: QUESTION ASKED ----------

    # Class 10 Maths – Quadratic Equations
    if "x^2" in text or "x²" in text or "quadratic" in text:
        return (
            "This concept appears frequently as a 4–5 mark question in CBSE exams.\n\n"
            "Before solving, what is the standard form of a quadratic equation?"
        )

    # Class 12 Physics – Electrostatics
    if "electric field" in text or "coulomb" in text:
        return (
            "This is a high-weight concept in Class 12 Physics board exams.\n\n"
            "What physical quantity does Coulomb’s law help you calculate first?"
        )

    # ---------- STAGE 1: STUDENT ATTEMPT ----------

    # Student replies with standard quadratic form
    if "ax²" in text or "ax^2" in text or "ax2" in text:
        return (
            "Good. You’ve recalled the standard form.\n\n"
            "In this form, which term helps you decide the nature of the roots?"
        )

    # Student replies vaguely or incorrectly
    if "formula" in text or "solve" in text:
        return (
            "Instead of applying a formula directly,\n\n"
            "what property of the equation should you examine first?"
        )

    # ---------- FALLBACK ----------

    return (
        "Let’s slow down and think.\n\n"
        "What chapter or concept from your syllabus does this relate to?"
    )
