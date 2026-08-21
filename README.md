# Keep Working Out

> "Surpass your limits. Master the fundamentals."

A smart, minimal, and lightning-fast fitness tracking web application built with Python and Streamlit. Designed to keep you accountable through consistency streaks, natural language logging, and a robust offline-first architecture.

**Live Demo:** [https://keepworkingout.streamlit.app](https://keepworkingout.streamlit.app)

---

## Features

* **Natural Language Parsing:** Log your workouts simply by typing sentences like *"10 pushups, 30 kg deadlift"*. The app extracts exercises, weights, and reps automatically.
* **Smart Failover Architecture:** Never lose your workflow when API limits are hit. It contains a seamless offline fallback parser that instantly switches to a robust local regex-based engine if Hugging Face API tokens run out.
* **Consistency Heatmap & Streaks:** Visual calendar tracker that mathematically locks your streak. Streaks only increase when you actively complete a session or log your day, keeping your data honest.
* **Dynamic Routine Generator:** Automatically builds personalized workout plans based on your target muscle group focus and available equipment (Gym vs. Bodyweight-only).
* **Secure User Workspaces:** Built-in account authentication backed by a local SQLite database to safely isolate your personal exercise arsenal and performance logs.

---

## Tech Stack

* **Frontend & UI:** Streamlit (Custom styled with a sleek "Shadow & Silk" dark aesthetic)
* **Database:** SQLite (Relational storage for users, performance logs, muscle arsenal, and streaks)
* **AI / NLP Engine:** Hugging Face Inference Client (`meta-llama/Llama-3.1-8B-Instruct`)
* **Data Manipulation:** Pandas
