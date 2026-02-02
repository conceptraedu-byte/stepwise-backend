def socratic_reply(user_text: str) -> str:
    text = user_text.lower()

    # Class 10 Maths – Quadratic Equations
    if "quadratic" in text or "x²" in text or "x^2" in text:
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

    return (
        "This looks like a board-exam problem.\n\n"
        "Before jumping ahead, what concept do you think this question is testing?"
    )
