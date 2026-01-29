# Messaging & IM Improvement Plan

This document outlines a concrete plan for **1-on-1 messaging**, **department/group messaging**, and **other IM improvements** in the school management system, based on the current codebase.

---

## Current State

### What exists today

| Feature | Backend | Web UI | Notes |
|--------|---------|--------|--------|
| **1-on-1 (direct) messages** | ✅ `Message` model (sender, recipient, subject, body, is_read, parent_message) | ❌ No dedicated page | API only: `MessageViewSet` with list, create, mark_read, **conversations** |
| **Group / department threads** | ✅ `MessageThread` (CLASSROOM, DEPARTMENT, ROLE, GLOBAL) + `ThreadMessage`, `ThreadReadState` | ✅ Message Groups (`/communication/groups/`) | Create, detail, join, leave, manage |
| **Messages landing** | ✅ `user_messages` view | ✅ `/accounts/messages/` | Shows **group threads only** (parent/teacher); no direct inbox |
| **Read state** | ✅ `Message.is_read`; `ThreadReadState` per user/thread | Partial (unread badge on threads) | Could expose “Seen” in UI |

So: **1-on-1 data and API exist; the missing piece is a web UI for direct conversations.** Group/department messaging is already in place; we can better surface it from the main Messages page.

---

## Proposed Direction

### 1. One place for all messaging: “Messages” hub

- **Single entry:** Keep **Messages** in the sidebar (one link).
- **Two clear areas on the Messages page:**
  - **Direct messages** – 1-on-1 conversations (using existing `Message` model and API).
  - **Group chats** – Department/class/role threads (existing Message Groups); can be embedded or linked.

This gives staff and teachers: “Messages” → Direct + Groups, without duplicating sidebar items.

---

## Phase 1: 1-on-1 (direct) messaging UI

**Goal:** Users can see their direct conversations and open a thread with a specific user, send and reply, and see read state.

### 1.1 Backend (minimal)

- **Conversation list:** Reuse the API’s “conversations” concept: for the current user, get distinct partners (from `Message`: sender/recipient), last message per partner, and unread count. You can add a small helper in `communication` or `accounts` that returns this for server-rendered views.
- **Thread view:** One view that, given `other_user_id`, returns all `Message` rows between `request.user` and that user (ordered by `created_at`), and supports POST to send a new message (and optionally mark received messages as read).
- **URLs (suggested):**
  - `GET /accounts/messages/` – Messages hub (see 1.2).
  - `GET /accounts/messages/direct/` – Direct inbox (conversation list).
  - `GET /accounts/messages/direct/<int:user_id>/` – Thread with user X; form to send/reply.
  - Optional: `POST /accounts/messages/direct/<int:user_id>/send/` for sending (or same URL with POST).

No new models required; use existing `Message` and existing API logic (e.g. `conversations` + thread query).

### 1.2 Messages hub page (Direct + Groups)

- **Tabs or sections:**
  - **Direct** – List of 1-on-1 conversations (avatar, name, last message snippet, time, unread badge). Click → thread with that user.
  - **Groups** – List of group threads the user belongs to (current behaviour from `class_threads_for_*` / `_serialize_thread`). Click → existing `communication:group_detail`. Add a link: “Manage groups” → `communication:group_list` (do not change Message Groups behaviour; only link from here).
- **Empty states:** “No direct messages yet” / “No group threads” with short guidance (e.g. “Start a conversation from a user’s profile” or “Ask admin to add you to a department group”).

### 1.3 Thread UI (direct)

- **Layout:** Simple two-panel or single column: message bubbles (or list) in chronological order; at bottom, text area + “Send”.
- **Behaviour:** On open, mark messages where I am the recipient as `is_read=True`. Show “Read” or “Seen” for messages I sent when the recipient has read them (use `Message.is_read` from recipient’s side when you have it).
- **Compose from elsewhere:** Optional: “Message” button on user profile or people list that links to `accounts:direct_thread` with that user’s id.

---

## Phase 2: Department / group messaging (clarify and link)

**Goal:** Make it obvious that “Groups” = department/class/role chats, and keep Message Groups untouched.

- **No changes to Message Groups app** – No change to `group_list`, `group_detail`, create/manage/join/leave.
- **On the Messages hub:** “Groups” tab/section shows the same thread list as today (department + class threads user is in), with:
  - Optional label or icon “Department” / “Class” per thread (from `MessageThread.scope` / department/classroom).
  - “Manage groups” / “All groups” → `communication:group_list`.
- **Sidebar:** Keep a single “Messages” entry; “Message Groups” can stay as a separate link for power users who want to go straight to group management, or be removed from sidebar and only reached via “Manage groups” from the hub. (Your earlier preference: do not touch Message Groups; so we only add links from the hub.)

---

## Phase 3: Optional IM improvements

These can be done incrementally after Phase 1–2.

| Improvement | Effort | Notes |
|-------------|--------|--------|
| **Read receipts in UI** | Low | Show “Seen” for direct messages when recipient has `is_read=True`; for groups use `ThreadReadState.last_read_at` to infer “read up to here”. |
| **Unread badge in sidebar** | Low | Sum of: (1) unread `Message` count for current user, (2) unread count from group threads (existing logic). Show next to “Messages” in nav. |
| **Notifications on new message** | Medium | On send, create an in-app (or email) notification for recipient; hook into existing notification system if present. |
| **“Start conversation” from profile** | Low | On user profile / staff list, add “Message” → `direct_thread` with that user. |
| **Typing indicators** | High | Requires WebSockets or frequent polling; suggest deferring. |
| **Rich text / attachments** | Medium | `Message.body` is text; optional: allow file attachments (new model or existing attachment pattern) and simple HTML/markdown. |

---

## Summary

- **1-on-1:** Add web UI (Messages hub with Direct tab, conversation list, thread view, send/reply) using existing `Message` model and existing API (conversations, create, mark_read). No new models.
- **Department/group:** Keep Message Groups as-is; surface group threads on the Messages hub under “Groups” and link to “Manage groups” for full group list.
- **Other IM:** Add read receipts in UI, unread badge in sidebar, optional “Message” from profile and notifications, in later phases.

If you confirm this direction, next step is implementing **Phase 1** (Messages hub with Direct + Groups, plus direct thread view and send/reply).
