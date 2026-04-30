def get_gravity_steps():
    return [
        {
            "type": "concept",
            "question": "What is gravity?",
            "expected_answer": "force of attraction between masses",
            "input_mode": "short",
            "options": [],
            "common_mistakes": [
                {
                    "pattern": "earth",
                    "type": "incomplete_concept",
                    "feedback": "Gravity is not only about Earth. It applies between any two masses.",
                    "hint": "Think universal"
                }
            ]
        },
        {
            "type": "formula",
            "question": "What is the formula of gravitational force?",
            "expected_answer": "F = G m1 m2 / d^2",
            "input_mode": "short",
            "options": [],
            "common_mistakes": [
                {
                    "pattern": "d",
                    "type": "formula_error",
                    "feedback": "You are missing the square on distance.",
                    "hint": "Inverse square law"
                }
            ]
        },
        {
            "type": "application",
            "question": "If distance doubles, what happens to force?",
            "expected_answer": "one fourth",
            "input_mode": "mcq",
            "options": ["double", "half", "one fourth", "same"],
            "common_mistakes": [
                {
                    "pattern": "half",
                    "type": "conceptual_error",
                    "feedback": "You assumed linear decrease.",
                    "hint": "Square relationship"
                }
            ]
        }
    ]