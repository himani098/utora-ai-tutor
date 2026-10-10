# Utora — your personal learning studio

Utora is a small, beginner-friendly learning app. Set a goal, choose how you like to learn, and build a personal course. You can try the included machine-learning lessons without an AI key. When you choose to connect Gemini, Utora can create a curriculum, explain a lesson in context, answer follow-up questions, and turn a voice recording into a question.

The app also saves lesson completion, quiz scores, and topic check-ins. It can download lesson notes and create a short MP4 with visual slides. Utora is an educational helper, not a replacement for a teacher or a source of guaranteed answers.

## What you can do

- Create a personal learning profile with a goal, daily study time, starting point, schedule, and teaching style.
- Try the built-in machine-learning sample course without a key. It is labeled as sample content, not AI-generated.
- Ask Gemini to create a real four-lesson curriculum based on your preferences.
- Read clear explanations and worked examples; ask a lesson-aware tutor follow-up questions.
- Keep each lesson’s tutor conversation, progress, and quiz history when you return with your passphrase.
- Record a voice question for transcription and tutoring. Tutor answers can also be spoken with your browser’s voice.
- Take multiple-choice quizzes, see your score and answer explanations, and spot topics that may need practice.
- Download a lesson as Markdown, search YouTube for related lessons, and create, play, or download a lesson MP4.
- Lock your profile or permanently delete its encrypted learning data.

## Start on your computer

You need Python 3.11 or newer. Streamlit is already installed in some Python environments; the command below installs this app’s listed packages into the Python environment you choose.

1. Open this project folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create and activate a private environment:

   **Windows PowerShell**

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, open a Command Prompt terminal and run:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate.bat
   ```

4. Install the app packages:

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. Start Utora:

   ```powershell
   python -m streamlit run app.py
   ```

   Streamlit prints a local web address. Open it in your browser.

You can try **Add the machine-learning sample course** without an API key. To create your own AI curriculum, ask Gemini for lesson explanations, or use voice transcription, connect a Gemini key as described below. A key is not needed to complete local setup or try quizzes, notes, progress, and video creation on the sample course.

## Gemini key: keep it private

Get your own key through Google AI Studio. Never paste a real key into `app.py`, `README.md`, a screenshot, or a public GitHub commit.

For local use, the sidebar key box is temporary to your current browser session. It is not written to the profile database. For a more private local setup:

1. In the project folder, make sure the `.streamlit` configuration folder exists.
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
3. Open `.streamlit/secrets.toml` and replace `paste-your-own-key-here` with your key, keeping the quotation marks:

   ```toml
   "Gemini API key" = "your-real-key-goes-here"
   ```

4. Save the file and restart Utora.

The exact Streamlit secret name is `Gemini API key`. Because that name contains spaces, keep it quoted in TOML. Utora also accepts the environment variable or Streamlit secret `GEMINI_API_KEY` for backward compatibility. A `GEMINI_API_KEY` environment variable takes priority if it is set. The real `.streamlit/secrets.toml` is excluded by `.gitignore`; only the example template belongs in Git. Never paste the real value into the app source, screenshots, logs, or GitHub.

On Streamlit Community Cloud, add `"Gemini API key"` in your app’s **Settings → Secrets** (or use the backward-compatible `GEMINI_API_KEY` name) instead of uploading your local secrets file. You can optionally set `GEMINI_MODEL` (the default is `gemini-3.8-flash`).

Utora sends a request to Google Gemini only after you select an AI action. It sends the prompt and relevant course/lesson context needed for that action. Voice audio is sent to Gemini for transcription only when you press **Transcribe and ask**. Do not send private, confidential, or regulated information to an AI service. Review Google’s current policies, model availability, and free-tier limits before using the service.

## Your profile and learning data

- Use a nickname, not an email address.
- A passphrase with at least 12 characters encrypts your saved profile, learning paths, lesson conversations, and progress before they are written to the local SQLite database.
- The passphrase is not saved and there is no recovery option. If you forget it, create a new profile; the old encrypted data cannot be unlocked.
- The Gemini key is kept separate from the encrypted learning profile.
- Select **Privacy → Delete my profile and all its data** to remove the profile and its saved records from this app’s database.
- On your computer, the database is at `%USERPROFILE%\.utora\learning.sqlite3` on Windows or `~/.utora/learning.sqlite3` on macOS/Linux. Keep a backup only if you can protect it.

Encryption protects the saved learning records, but it does not make a shared computer or public hosting environment risk-free. Use a strong device password and a pseudonym. On free cloud hosting, the service operates the app, and local files can be removed during a sleep/redeploy cycle. Do not use the free app as durable or regulated-data storage.

## Share it with GitHub

1. Create a new, **private** repository on GitHub if you want to keep your project private.
2. In VS Code, open **Source Control**, review every file, and make sure no real API key or `secrets.toml` is included. `.gitignore` excludes the local secret file and database.
3. Stage the project files, create a commit, and push to your repository.
4. For a public repository, remove any personal information from course content and commit history before publishing.

You can also use GitHub’s terminal if Git is installed:

```powershell
git init
git add .
git status
git commit -m "Build Utora personal learning app"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/YOUR-REPOSITORY.git
git push -u origin main
```

Replace the example repository address with your own. `git status` is included so you can check what will be shared before making the first commit. Do not continue if it lists a real key or private data.

## Free Streamlit Community Cloud deployment

1. Push your project to GitHub, including `app.py`, `tutor_app/`, `requirements.txt`, and `.streamlit/config.toml`.
2. Sign in to Streamlit Community Cloud with GitHub and choose **Create app**.
3. Select your repository, branch, and `app.py` as the main file.
4. In the app’s settings, add a secret named `GEMINI_API_KEY` only if you want the Gemini features. Keep it out of GitHub.
5. Deploy. Test the sample course first, then test your own key privately.

Community Cloud plans, resource limits, sleep behavior, video memory limits, and available Python versions may change. MP4 video creation temporarily uses memory for designed slides and works best with short lessons. This starter app uses local SQLite, so free-host data is not guaranteed to persist across restarts, sleep, or redeployment. For durable shared cloud accounts, plan a separately secured database and review its costs and privacy design before collecting user data.

## Reset and recover

- **Lock:** Choose **Lock this profile** in the sidebar. This clears the unlocked key from the app session.
- **Delete one profile:** Open **Privacy**, choose delete, and confirm. Its saved courses, preferences, tutor messages, and progress are removed.
- **Forget the passphrase:** It cannot be recovered. The app never stores it.
- **Reset a local installation:** First, use the in-app delete action if you need to remove a profile. To remove the entire local database, stop Utora and delete only `%USERPROFILE%\.utora\learning.sqlite3` (and its matching `learning.sqlite3-wal` / `learning.sqlite3-shm` files if present). This removes every local profile in that database. Do not run this command against an unverified path.
- **Rotate a leaked key:** Revoke it in Google AI Studio, create a replacement, and update local secrets or Community Cloud secrets. Never commit either key.

## Troubleshooting

- **`streamlit` is not found:** Activate the project environment and run `python -m pip install -r requirements.txt` again.
- **Gemini rejects the key:** Check the key, the enabled API, your internet connection, and the current quota. Utora does not display raw keys in error messages.
- **The browser cannot record audio:** Allow microphone access and use a current browser with audio input support. Typing questions does not require a microphone.
- **The MP4 is unavailable:** Confirm the package installation completed. Video creation uses the included FFmpeg binary and may be limited by cloud memory.
- **The profile does not unlock:** Check the nickname spelling and passphrase. The nickname is case-insensitive; the passphrase is not. There is no passphrase reset.

## For contributors

Run the focused built-in checks:

```powershell
python -m unittest discover -s tests -v
```

The tests cover encrypted save/unlock/delete behavior, sample course structure, quiz validation, contextual tutoring requests, and API-key handling. An actual Gemini answer requires a working private API key and network access; a successful offline test does not claim that a live Gemini call was made.
