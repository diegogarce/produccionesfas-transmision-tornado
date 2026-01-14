# PYTHON TORNADO DEMO: FULL SCOPE SPECIFICATION

## 1. Project Context
Create a **Live Streaming Demo Platform** using **Python (Tornado)** and **MySQL** on Windows.
The system requires User Registration, a Video Player with Real-time interactions, Roles (Moderator/Speaker), and Analytics Reports.

## 2. Technical Stack
- **Backend:** Python 3.x, Tornado Web Server.
- **Database:** MySQL (via `pymysql` driver).
- **Frontend:** HTML5, CSS3, Vanilla JS (No frameworks).
- **Auth:** Cookie-based session after Registration.

## 3. Database Schema (Already created)
- `users`: id, name, email, phone.
- `chat_messages`: id, user_id, user_name, message.
- `questions`: id, user_id, user_name, question_text, status.
- `session_analytics`: id, user_id, start_time, last_ping, total_minutes.

## 4. Required Pages (Routes & Logic)

### A. Registration (`/`) - ENTRY POINT
- Form fields: **Name**, **Email**, **Phone**.
- **Logic:**
    - Check if email exists. If yes, log user in. If no, create user and log in.
    - Set a secure cookie with `user_id`.
    - Redirect to `/watch`.

### B. Player Room (`/watch`) - Protected
- **Layout:** Video Iframe (left), Tabs for Chat & Q&A (right).
- **Real-Time Logic:**
    - **Chat:** Send/Receive messages via WebSocket.
    - **Q&A:** Ask questions (User view). See approved questions.
    - **Heartbeat (Analytics):**
        - JavaScript must send a JSON `{type: 'ping'}` every 60 seconds via WebSocket.
        - Backend updates `session_analytics` table: Update `last_ping` and increment `total_minutes`.

### C. Moderator Dashboard (`/mod`)
- **Chat View:** See all messages.
- **Q&A Management:** List "Pending" questions with an "Approve" button.
- **Logic:** Clicking approve sends a WS message `{type: 'approve', id: ...}` which moves it to the Speaker view.

### D. Speaker Dashboard (`/speaker`)
- **View:** Clean, large font list of ONLY `status='approved'` questions. Real-time updates.

### E. Reports Section (`/reports`)
- **Tab 1: Registered Users:** Table showing Name, Email, Phone, Reg Date (Select from `users`).
- **Tab 2: Analytics:** Table showing User Name, Login Time, Last Active, **Total Minutes Watched** (Select from `session_analytics` JOIN `users`).

## 5. WebSocket Handler Logic (`ws`)
Handle JSON payloads:
1.  `chat`: Insert DB -> Broadcast to All.
2.  `ask`: Insert DB -> Broadcast to Moderators.
3.  `approve`: Update DB -> Broadcast to Speaker/Viewers.
4.  `ping`: Update `session_analytics` for the current `user_id`. Do NOT broadcast.

## 6. Deliverables
Generate the following files:
1.  `server.py`: Complete Tornado application with MySQL connection, Handlers, and WebSocket logic.
2.  `templates/register.html`: CSS styled registration form.
3.  `templates/watch.html`: Player with Chat/Q&A and **JS Heartbeat interval**.
4.  `templates/moderator.html`: Mod controls.
5.  `templates/speaker.html`: Speaker view.
6.  `templates/reports.html`: Tables for data reporting.