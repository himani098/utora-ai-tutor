from __future__ import annotations

import base64
import hashlib
import html
import os
from datetime import date
from urllib.parse import quote_plus

import streamlit as st
import streamlit.components.v1 as components
from streamlit.errors import StreamlitSecretNotFoundError

from tutor_app.configuration import resolve_gemini_api_key
from tutor_app.course import CourseError, create_ai_course, create_sample_course, make_lesson_notes
from tutor_app.gemini import GeminiError, answer_question, transcribe_audio
from tutor_app.media import VideoBuildError, make_video
from tutor_app.security import ProfileError
from tutor_app.storage import DataStoreError, Repository, database_path

st.set_page_config(
    page_title="Utora — your personal learning studio",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #f5f7fb; }
    [data-testid="stSidebar"] { background: #111b2d; }
    [data-testid="stSidebar"] * { color: #edf3ff; }
    [data-testid="stSidebar"] [data-baseweb="input"] *,
    [data-testid="stSidebar"] [data-baseweb="select"] * { color: #17233a; }
    .utora-hero { padding: 1.65rem 1.9rem; border-radius: 22px; color: #fff;
      background: linear-gradient(120deg,#13213a 0%,#263d64 62%,#496cb6 100%);
      margin: .2rem 0 1.3rem; }
    .utora-hero h1 { color: #fff; margin: .35rem 0; font-size: 2.1rem; }
    .utora-hero p { color: #e3ebfb; margin: 0; font-size: 1.02rem; }
    .utora-eyebrow { color: #a9c0ff; text-transform: uppercase;
      letter-spacing: .13em; font-size: .74rem; font-weight: 700; }
    div[data-testid="stMetric"] { background: #fff; border: 1px solid #e5eaf2;
      border-radius: 15px; padding: 1rem; }
    .stButton > button, .stDownloadButton > button { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

NAVIGATION = (
    "Overview",
    "Learning plan",
    "Lessons & tutor",
    "Practice",
    "Progress",
    "Study studio",
    "Privacy",
)


@st.cache_resource
def get_repository() -> Repository:
    return Repository(database_path())


def get_api_key() -> str:
    try:
        secrets = st.secrets
    except StreamlitSecretNotFoundError:
        secrets = None
    return resolve_gemini_api_key(os.environ, secrets)


def get_profile(repository: Repository) -> dict:
    return repository.get(
        st.session_state["profile_id"], st.session_state["vault_key"], "profile", "settings"
    ) or {}


def get_courses(repository: Repository) -> list[dict]:
    return repository.list(
        st.session_state["profile_id"], st.session_state["vault_key"], "course"
    )


def record_value(repository: Repository, kind: str, key: str, default):
    return repository.get(
        st.session_state["profile_id"], st.session_state["vault_key"], kind, key
    ) or default


def hero(title: str, subtitle: str, eyebrow: str = "Your personal learning studio") -> None:
    st.markdown(
        f'<section class="utora-hero"><div class="utora-eyebrow">{html.escape(eyebrow)}</div>'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></section>",
        unsafe_allow_html=True,
    )


def login_screen(repository: Repository) -> None:
    hero("Meet Utora", "A thoughtful study partner for the goals you care about.", "A private learning space")
    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        st.subheader("Create or unlock your learning profile")
        st.write(
            "Choose a memorable nickname (not your email) and a private passphrase. "
            "Your goals, lessons, quizzes, and tutor history are encrypted before saving."
        )
        with st.form("profile-unlock"):
            handle = st.text_input("Private nickname", max_chars=32, placeholder="For example: learner_7")
            passphrase = st.text_input("Passphrase", type="password", max_chars=256)
            confirmation = st.text_input("Repeat passphrase for a new profile", type="password", max_chars=256)
            submitted = st.form_submit_button("Continue securely", type="primary", use_container_width=True)
        if submitted:
            try:
                profile_id, vault_key, created = repository.unlock_or_create(handle, passphrase, confirmation)
                st.session_state["profile_id"] = profile_id
                st.session_state["vault_key"] = vault_key
                st.session_state["display_handle"] = handle.strip()
                st.session_state["profile_created"] = created
                st.rerun()
            except ProfileError as exc:
                st.error(str(exc))
            except DataStoreError as exc:
                st.error(f"The private learning vault could not be opened: {exc}")
    with right:
        st.markdown("### Made for steady progress")
        st.markdown(
            "- Choose a goal that fits your week\n"
            "- Learn with clear examples and practice\n"
            "- Keep a private record of what you have learned\n"
            "- Bring your own Gemini key only when you choose to use AI"
        )
        st.info(
            "Your passphrase is never saved. If you forget it, encrypted notes cannot be recovered. "
            "Your Gemini key is separate and is never stored in the learning vault."
        )


def render_sidebar(repository: Repository, courses: list[dict]) -> tuple[str, str, bool]:
    with st.sidebar:
        st.markdown("## Utora")
        st.caption(f"Welcome, {st.session_state.get('display_handle', 'learner')}")
        page = st.radio("Your studio", NAVIGATION, label_visibility="collapsed")
        if courses:
            options = [course["course_id"] for course in courses]
            current = st.session_state.get("active_course_id")
            index = options.index(current) if current in options else 0
            course_id = st.selectbox(
                "Learning path",
                options,
                index=index,
                format_func=lambda value: next(
                    f"{course['title']} · {'AI' if course['ai_generated'] else 'sample'}"
                    for course in courses if course["course_id"] == value
                ),
            )
            st.session_state["active_course_id"] = course_id
        else:
            st.caption("No course yet — create one or try the offline sample.")

        st.divider()
        with st.expander("Connect Gemini AI", expanded=not bool(get_api_key())):
            session_key = ""
            configured_key = get_api_key()
            if configured_key:
                st.success("A Gemini key is configured.")
                st.caption("Keys from secrets or the environment are never shown here.")
            else:
                session_key = st.text_input(
                    "Gemini API key",
                    type="password",
                    key="session-gemini-key",
                    help="Used only in this browser session. For safer setup, use a private environment secret.",
                    placeholder="Paste only when you are ready to use AI",
                ).strip()
                st.caption("This field is not saved in your profile or database.")
            api_key = configured_key or session_key
            consent = st.checkbox(
                "I agree to send the prompt and lesson context to Google Gemini when I use AI.",
                key="gemini-data-consent",
            )
            st.caption("No key? Your sample course and local progress still work.")

        st.divider()
        if st.button("Lock this profile", use_container_width=True):
            st.session_state["clear-session-gemini-key"] = True
            for key in ("profile_id", "vault_key", "display_handle", "active_course_id"):
                st.session_state.pop(key, None)
            st.rerun()
    return page, api_key, consent


def render_overview(repository: Repository, courses: list[dict], profile: dict) -> None:
    goal = profile.get("goal") or "Choose a goal, and we’ll make a plan that fits your life."
    hero(
        f"Good to see you, {st.session_state.get('display_handle', 'learner')}.",
        goal,
        f"Your learning studio · {date.today().strftime('%A, %B %d')}",
    )
    course = selected_course(courses)
    completed, attempts = [], []
    if course:
        completed = record_value(repository, "progress", f"{course['course_id']}:completions", [])
        attempts = record_value(repository, "progress", f"{course['course_id']}:attempts", [])
    question_count = sum(item.get("question_count", 0) for item in attempts)
    average = sum(item.get("score", 0) for item in attempts) / len(attempts) if attempts else 0
    metrics = st.columns(4)
    metrics[0].metric("Learning paths", len(courses))
    metrics[1].metric("Lessons completed", len(completed))
    metrics[2].metric("Practice questions", question_count)
    metrics[3].metric("Practice average", f"{average:.0f}%" if attempts else "—")

    if course:
        next_lesson = next(
            (lesson for lesson in course["lessons"] if lesson["lesson_id"] not in completed),
            course["lessons"][0],
        )
        st.subheader("Pick up where you left off")
        st.markdown(f"**{course['title']}**")
        st.write(f"Next up: **{next_lesson['title']}** — {next_lesson['objective']}")
        if not course["ai_generated"]:
            st.info("This is an offline sample course, not an AI-generated curriculum.")
        st.caption("Choose **Lessons & tutor** in the sidebar to continue.")
    else:
        st.subheader("A good first step")
        st.write("Tell Utora what you want to learn and how much time you have.")

    topic_scores: dict[str, list[int]] = {}
    for attempt in attempts:
        for topic, (correct, total) in attempt.get("topic_scores", {}).items():
            score = topic_scores.setdefault(topic, [0, 0])
            score[0] += correct
            score[1] += total
    needs_help = [
        (topic, correct / total)
        for topic, (correct, total) in topic_scores.items()
        if total and correct / total < 0.7
    ]
    if needs_help:
        st.subheader("A little extra practice may help")
        for topic, ratio in sorted(needs_help, key=lambda item: item[1]):
            st.warning(f"**{topic}** — {ratio:.0%} so far. Revisit the example, then try a fresh question.")
    elif attempts:
        st.success("Nice work — no topic is currently below the 70% check-in.")
    st.caption(
        f"Plan: {profile.get('minutes_per_day', 20)} minutes/day · "
        f"{profile.get('teaching_style', 'Example first')} · "
        f"{profile.get('study_days', 'Flexible schedule')}"
    )


def render_plan(repository: Repository, api_key: str, consent: bool) -> None:
    st.header("Shape your learning plan")
    st.write("Your preferences are saved privately. Nothing is sent to AI until you request an AI action.")
    profile = get_profile(repository)
    styles = ["Example first", "Clear and concise", "Socratic questions", "Visual and structured"]
    rhythms = ["Flexible schedule", "Weekdays", "Weekends", "Every day"]
    levels = ["New to this", "Know a little", "Comfortable with the basics"]
    with st.form("learning-preferences"):
        goal = st.text_area(
            "What would you like to learn?",
            value=profile.get("goal", ""),
            max_chars=500,
            placeholder="For example: Understand machine learning and build my first small project.",
        )
        left, right = st.columns(2)
        with left:
            minutes = st.slider("Time each day", 5, 120, int(profile.get("minutes_per_day", 20)), step=5)
            style = st.selectbox("How should lessons feel?", styles, index=_choice_index(styles, profile.get("teaching_style")))
        with right:
            rhythm = st.selectbox("Your rhythm", rhythms, index=_choice_index(rhythms, profile.get("study_days")))
            level = st.selectbox("Starting point", levels, index=_choice_index(levels, profile.get("experience")))
        save = st.form_submit_button("Save my learning preferences", type="primary")
    if save:
        if not goal.strip():
            st.error("Add a learning goal before saving.")
        else:
            repository.put(
                st.session_state["profile_id"],
                st.session_state["vault_key"],
                "profile",
                "settings",
                {
                    "goal": goal.strip(),
                    "minutes_per_day": minutes,
                    "teaching_style": style,
                    "study_days": rhythm,
                    "experience": level,
                },
            )
            st.success("Your preferences are saved in your encrypted profile.")
            st.rerun()

    profile = get_profile(repository)
    st.divider()
    st.subheader("Create your curriculum")
    if not profile.get("goal"):
        st.info("Save a learning goal above before generating a curriculum.")
    if st.button("Generate my AI curriculum", type="primary", disabled=not bool(profile.get("goal"))):
        if not api_key:
            st.error("Add a Gemini API key in the sidebar when you are ready to create an AI curriculum.")
        elif not consent:
            st.error("Check the Gemini data-sharing consent in the sidebar first.")
        else:
            with st.spinner("Designing your personal curriculum with Gemini…"):
                try:
                    course = create_ai_course(api_key, profile)
                    repository.put(
                        st.session_state["profile_id"], st.session_state["vault_key"],
                        "course", course["course_id"], course,
                    )
                    st.session_state["active_course_id"] = course["course_id"]
                    st.success(f"Your AI-generated path, **{course['title']}**, is ready.")
                    st.rerun()
                except (GeminiError, CourseError) as exc:
                    st.error(f"Curriculum generation did not complete: {exc}")
    st.caption("For this action, your saved preferences and course request are sent to Google Gemini.")

    st.divider()
    st.subheader("Try an offline sample")
    st.caption("A built-in machine-learning mini-course is provided for trying the app; it is not AI-generated.")
    if st.button("Add the machine-learning sample course"):
        course = create_sample_course()
        repository.put(
            st.session_state["profile_id"], st.session_state["vault_key"],
            "course", course["course_id"], course,
        )
        st.session_state["active_course_id"] = course["course_id"]
        st.rerun()


def speak_answer(text: str) -> None:
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    components.html(
        f"""
        <button id="speak" style="border:1px solid #ccd6e8;border-radius:9px;padding:8px 12px;background:white;cursor:pointer">
          🔊 Speak this answer
        </button><span id="status" style="margin-left:10px;font:14px system-ui;color:#30415f"></span>
        <script>
          const bytes = Uint8Array.from(atob("{encoded}"), c => c.charCodeAt(0));
          const answer = new TextDecoder().decode(bytes);
          document.getElementById("speak").addEventListener("click", () => {{
            if (!("speechSynthesis" in window)) {{
              document.getElementById("status").textContent = "Speech is not supported by this browser.";
              return;
            }}
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(answer);
            utterance.rate = 0.95;
            window.speechSynthesis.speak(utterance);
            document.getElementById("status").textContent = "Playing with your browser's voice.";
          }});
        </script>
        """,
        height=45,
    )


def submit_question(
    repository: Repository,
    course: dict,
    lesson: dict,
    question: str,
    api_key: str,
    consent: bool,
    audio_id: str | None = None,
) -> None:
    question = question.strip()
    if not question:
        st.warning("Write or record a question first.")
        return
    if len(question) > 3000:
        st.warning("Please keep a question under 3,000 characters.")
        return
    if not api_key:
        st.error("Connect Gemini in the sidebar to ask the AI tutor. Your question was not saved.")
        return
    if not consent:
        st.error("Please check the Gemini data-sharing consent in the sidebar before asking.")
        return

    record_key = f"{course['course_id']}:{lesson['lesson_id']}"
    history = record_value(repository, "chat", record_key, [])
    try:
        answer = answer_question(
            api_key,
            course,
            lesson,
            question,
            history,
            get_profile(repository).get("teaching_style", "Example first"),
        )
    except GeminiError as exc:
        st.error(f"The tutor could not answer: {exc}")
        return
    history.extend([{"role": "user", "text": question}, {"role": "assistant", "text": answer}])
    repository.put(
        st.session_state["profile_id"], st.session_state["vault_key"], "chat", record_key, history[-200:]
    )
    if audio_id:
        st.session_state["last-voice-question"] = audio_id
    st.rerun()


def render_lessons(repository: Repository, course: dict | None, api_key: str, consent: bool) -> None:
    st.header("Learn and ask")
    if not course:
        st.info("Create a learning plan or add the offline sample to start a lesson.")
        return
    lessons = {lesson["lesson_id"]: lesson for lesson in course["lessons"]}
    lesson_id = st.selectbox(
        "Choose a lesson", list(lessons),
        format_func=lambda value: lessons[value]["title"],
        key=f"lesson-{course['course_id']}",
    )
    lesson = lessons[lesson_id]
    st.markdown(f"### {lesson['title']}")
    st.caption(f"**Learning outcome:** {lesson['objective']}")
    st.markdown(f"**Key ideas:** {' · '.join(lesson['concepts'])}")
    st.markdown("#### The idea")
    st.write(lesson["explanation"])
    st.markdown("#### A worked example")
    st.info(lesson["example"])
    completed = record_value(repository, "progress", f"{course['course_id']}:completions", [])
    if lesson_id in completed:
        st.success("This lesson is marked complete.")
    elif st.button("Mark this lesson complete", key=f"complete-{course['course_id']}-{lesson_id}"):
        completed.append(lesson_id)
        repository.put(
            st.session_state["profile_id"], st.session_state["vault_key"],
            "progress", f"{course['course_id']}:completions", completed,
        )
        st.rerun()

    st.divider()
    st.subheader("Your contextual AI tutor")
    if not course["ai_generated"]:
        st.caption("This is sample lesson context, not AI-generated. Tutor answers require Gemini.")
    record_key = f"{course['course_id']}:{lesson_id}"
    history = record_value(repository, "chat", record_key, [])
    if history:
        st.caption("Earlier questions and answers for this lesson are remembered privately.")
        for message in history[-12:]:
            with st.chat_message(message["role"]):
                st.markdown(message["text"])
                if message["role"] == "assistant":
                    speak_answer(message["text"])
    else:
        st.caption("The tutor remembers this lesson’s earlier questions for your next visit.")
    with st.form(f"question-{course['course_id']}-{lesson_id}", clear_on_submit=True):
        question = st.text_area("Ask about this lesson", max_chars=3000, placeholder="What would you like explained?")
        send = st.form_submit_button("Ask the Gemini tutor")
    if send:
        submit_question(repository, course, lesson, question, api_key, consent)

    with st.expander("Ask with your voice"):
        st.caption("Record a question. Gemini transcribes it and answers; the transcript is saved with this lesson.")
        audio = st.audio_input("Record your question", key=f"audio-{course['course_id']}-{lesson_id}")
        if audio:
            st.audio(audio)
            if st.button("Transcribe and ask", key=f"transcribe-{course['course_id']}-{lesson_id}"):
                audio_bytes = audio.getvalue()
                audio_id = hashlib.sha256(audio_bytes).hexdigest()
                if st.session_state.get("last-voice-question") == audio_id:
                    st.info("This recording was already sent in this session.")
                elif not api_key:
                    st.error("Connect Gemini in the sidebar to transcribe a voice question.")
                elif not consent:
                    st.error("Please check the Gemini data-sharing consent first.")
                else:
                    try:
                        with st.spinner("Transcribing your question…"):
                            transcription = transcribe_audio(api_key, audio_bytes, audio.type or "audio/webm")
                        if not transcription:
                            st.warning("No clear speech was found. Try a shorter recording.")
                        else:
                            st.info(f"Your question: {transcription}")
                            submit_question(repository, course, lesson, transcription, api_key, consent, audio_id)
                    except GeminiError as exc:
                        st.error(f"Voice transcription did not complete: {exc}")


def render_practice(repository: Repository, course: dict | None) -> None:
    st.header("Practice and reflect")
    if not course:
        st.info("Choose a learning path first. The offline sample includes practice questions.")
        return
    lessons = {lesson["lesson_id"]: lesson for lesson in course["lessons"]}
    lesson_id = st.selectbox(
        "Practice from a lesson", list(lessons),
        format_func=lambda value: lessons[value]["title"],
        key=f"quiz-lesson-{course['course_id']}",
    )
    quizzes = lessons[lesson_id]["quiz"]
    if not quizzes:
        st.info("This lesson has no quiz yet. Try the sample course for practice questions.")
        return
    with st.form(f"quiz-{course['course_id']}-{lesson_id}"):
        answers = []
        for number, item in enumerate(quizzes, start=1):
            st.markdown(f"**{number}. {item['question']}**")
            answers.append(
                st.radio(
                    f"Answer {number}", item["options"], index=None,
                    key=f"answer-{course['course_id']}-{lesson_id}-{number}",
                    label_visibility="collapsed",
                )
            )
        submitted = st.form_submit_button("Check my answers", type="primary")
    if submitted:
        if any(answer is None for answer in answers):
            st.warning("Answer every question before checking your result.")
        else:
            topic_scores: dict[str, list[int]] = {}
            correct_count = 0
            for answer, item in zip(answers, quizzes):
                correct = answer == item["options"][item["answer_index"]]
                correct_count += int(correct)
                score = topic_scores.setdefault(item["topic"], [0, 0])
                score[0] += int(correct)
                score[1] += 1
            score_pct = 100 * correct_count / len(quizzes)
            attempt_key = f"{course['course_id']}:attempts"
            attempts = record_value(repository, "progress", attempt_key, [])
            attempts.append(
                {
                    "score": score_pct,
                    "question_count": len(quizzes),
                    "topic_scores": topic_scores,
                    "lesson_id": lesson_id,
                }
            )
            repository.put(
                st.session_state["profile_id"], st.session_state["vault_key"],
                "progress", attempt_key, attempts[-500:],
            )
            st.session_state["last-quiz-result"] = {
                "course_id": course["course_id"],
                "lesson_id": lesson_id,
                "score": score_pct,
                "answers": answers,
            }
            st.rerun()
    result = st.session_state.get("last-quiz-result")
    if result and result["course_id"] == course["course_id"] and result["lesson_id"] == lesson_id:
        st.subheader(f"Your score: {result['score']:.0f}%")
        for number, (answer, item) in enumerate(zip(result["answers"], quizzes), start=1):
            correct = answer == item["options"][item["answer_index"]]
            st.markdown(
                f"{'✅' if correct else '↩️'} **{number}. {item['topic']}** — {item['explanation']}"
            )
        if result["score"] < 70:
            st.warning("Revisit the lesson examples, then try the practice again.")
        else:
            st.success("Strong work. Your score is included in your private progress.")


def render_progress(repository: Repository, course: dict | None) -> None:
    st.header("Your progress")
    if not course:
        st.info("Progress will appear after you start a learning path.")
        return
    completions = record_value(repository, "progress", f"{course['course_id']}:completions", [])
    attempts = record_value(repository, "progress", f"{course['course_id']}:attempts", [])
    total_questions = sum(item.get("question_count", 0) for item in attempts)
    average = sum(item.get("score", 0) for item in attempts) / len(attempts) if attempts else 0
    first, second, third = st.columns(3)
    first.metric("Path completion", f"{len(completions)}/{len(course['lessons'])}")
    second.metric("Questions attempted", total_questions)
    third.metric("Average score", f"{average:.0f}%" if attempts else "—")
    st.progress(len(completions) / len(course["lessons"]) if course["lessons"] else 0)
    st.caption("Completion uses lessons you mark done and practice quizzes you submit.")
    topic_scores: dict[str, list[int]] = {}
    for attempt in attempts:
        for topic, (correct, total) in attempt.get("topic_scores", {}).items():
            score = topic_scores.setdefault(topic, [0, 0])
            score[0] += correct
            score[1] += total
    st.subheader("Topic check-ins")
    if not topic_scores:
        st.write("Submit a quiz to see which ideas feel secure and which need another example.")
    for topic, (correct, total) in sorted(topic_scores.items()):
        ratio = correct / total if total else 0
        st.write(f"**{topic}** — {correct} of {total} correct")
        st.progress(ratio)
        if ratio < 0.7:
            st.warning(f"Try the lesson on **{topic}** again, explain it aloud, and retake its practice quiz.")
    st.subheader("Path at a glance")
    for lesson in course["lessons"]:
        mark = "✅" if lesson["lesson_id"] in completions else "○"
        st.write(f"{mark} **{lesson['title']}** — {lesson['objective']}")
    st.caption(f"Content source: {'AI-generated' if course['ai_generated'] else 'offline sample'}.")


def render_studio(course: dict | None) -> None:
    st.header("Study studio")
    if not course:
        st.info("Create a learning path before preparing notes and slides.")
        return
    lessons = {lesson["lesson_id"]: lesson for lesson in course["lessons"]}
    lesson_id = st.selectbox(
        "Study materials for", list(lessons),
        format_func=lambda value: lessons[value]["title"],
        key=f"studio-lesson-{course['course_id']}",
    )
    lesson = lessons[lesson_id]
    st.download_button(
        "Download lesson notes (.md)",
        data=make_lesson_notes(course, lesson),
        file_name=f"{course['course_id']}-{lesson_id}-notes.md",
        mime="text/markdown",
    )
    st.subheader("Related educational videos")
    query = quote_plus(f"{course['title']} {lesson['title']} explained")
    st.link_button(
        "Search YouTube for related lessons",
        f"https://www.youtube.com/results?search_query={query}",
    )
    st.caption("Opens YouTube search; individual video results are not verified by this app.")
    st.divider()
    st.subheader("Make a visual lesson video")
    st.write("Utora turns the lesson into designed slides and a short, playable MP4.")
    if st.button("Create my lesson MP4", type="primary", key=f"make-video-{course['course_id']}-{lesson_id}"):
        with st.spinner("Creating slides and rendering the video…"):
            try:
                st.session_state["lesson-video"] = {
                    "course_id": course["course_id"],
                    "lesson_id": lesson_id,
                    "bytes": make_video(course, lesson),
                }
            except VideoBuildError as exc:
                st.error(f"The video could not be created: {exc}")
    video = st.session_state.get("lesson-video")
    if video and video["course_id"] == course["course_id"] and video["lesson_id"] == lesson_id:
        st.video(video["bytes"])
        st.download_button(
            "Download the playable lesson MP4",
            data=video["bytes"],
            file_name=f"{course['course_id']}-{lesson_id}.mp4",
            mime="video/mp4",
            key=f"download-{course['course_id']}-{lesson_id}",
        )
        st.success("The MP4 was rendered locally and is playable above.")


def render_privacy(repository: Repository) -> None:
    st.header("Privacy and profile controls")
    st.write(
        "Your learning preferences, saved courses, lesson chats, and practice history are encrypted "
        "before they are written to the local database. Your passphrase is not saved."
    )
    st.code(str(database_path()), language="text")
    st.warning(
        "AI requests send the prompt and lesson context needed for that action to Google Gemini. "
        "Do not use AI features with confidential or regulated information. API keys are never placed in your learning vault."
    )
    st.info(
        "On a free cloud deployment, the hosting service runs this app and local SQLite files may be removed "
        "when an instance sleeps or is redeployed. Use a pseudonym and avoid sensitive personal details."
    )
    st.subheader("Reset this profile")
    st.write("Permanently delete this profile’s encrypted preferences, courses, chat history, and progress.")
    if st.button("Lock this profile now"):
        st.session_state["clear-session-gemini-key"] = True
        for key in ("profile_id", "vault_key", "display_handle", "active_course_id"):
            st.session_state.pop(key, None)
        st.rerun()
    if st.button("Delete my profile and all its data"):
        st.session_state["confirm-delete"] = True
    if st.session_state.get("confirm-delete"):
        st.error("This cannot be undone. Create a new profile to use Utora again.")
        confirmed = st.checkbox("I understand that all my encrypted learning data will be deleted.")
        if st.button("Confirm permanent deletion", disabled=not confirmed):
            try:
                repository.delete_profile(st.session_state["profile_id"])
                st.session_state["clear-session-gemini-key"] = True
                for key in (
                    "profile_id", "vault_key", "display_handle", "active_course_id",
                    "confirm-delete", "last-quiz-result", "lesson-video",
                ):
                    st.session_state.pop(key, None)
                st.rerun()
            except DataStoreError as exc:
                st.error(f"The profile could not be deleted: {exc}")


def _choice_index(options: list[str], value: str | None) -> int:
    return options.index(value) if value in options else 0


def selected_course(courses: list[dict]) -> dict | None:
    if not courses:
        return None
    active_id = st.session_state.get("active_course_id")
    return next(
        (course for course in courses if course["course_id"] == active_id),
        courses[0],
    )


def main() -> None:
    if st.session_state.pop("clear-session-gemini-key", False):
        st.session_state.pop("session-gemini-key", None)
        st.session_state.pop("gemini-data-consent", None)
    try:
        repository = get_repository()
    except DataStoreError as exc:
        st.error(f"Utora could not prepare the encrypted learning database: {exc}")
        st.stop()
    if "profile_id" not in st.session_state or "vault_key" not in st.session_state:
        login_screen(repository)
        return
    try:
        courses = get_courses(repository)
        profile = get_profile(repository)
    except DataStoreError as exc:
        st.error(f"Your encrypted profile data could not be read: {exc}")
        if st.button("Lock the profile and try again"):
            for key in ("profile_id", "vault_key", "display_handle"):
                st.session_state.pop(key, None)
            st.rerun()
        return
    page, api_key, consent = render_sidebar(repository, courses)
    course = selected_course(courses)
    try:
        if page == "Overview":
            render_overview(repository, courses, profile)
        elif page == "Learning plan":
            render_plan(repository, api_key, consent)
        elif page == "Lessons & tutor":
            render_lessons(repository, course, api_key, consent)
        elif page == "Practice":
            render_practice(repository, course)
        elif page == "Progress":
            render_progress(repository, course)
        elif page == "Study studio":
            render_studio(course)
        elif page == "Privacy":
            render_privacy(repository)
    except DataStoreError as exc:
        st.error(f"Utora could not save or read this learning data: {exc}")


if __name__ == "__main__":
    main()
