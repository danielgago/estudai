# Proposed issues from `notes.md`

These issue drafts are based on the current codebase and tests, not only on the raw notes. Each item below is written in terms of the current problem and the expected future behavior, without prescribing implementation.

## 1. Nested folder selections count parent and child as separate active study folders

**Problem**

The current study-scope summary is driven by the set of checked folder IDs, and the sidebar cascades a parent folder's checked state to its descendants. In practice, this means a parent folder and one of its subfolders can both count toward the visible selection summary at the same time. The result is a timer context that can report multiple folders selected even when the user experiences that choice as one study branch. This makes folder selection feel inflated and can blur the difference between selecting a hierarchy and selecting multiple unrelated decks.

**Expected future behavior**

The visible study-scope summary should match the user's mental model of the selection. Parent/child relationships inside the same branch should not produce confusing double-counting, and the app should describe the effective study scope in a way that stays intuitive when nested folders are involved.

## 2. Parent folders appear empty when their flashcards live in subfolders

**Problem**

Sidebar counts and progress are currently computed from flashcards stored directly in each folder. Because of that, a parent folder with zero direct cards but a large amount of material in child folders can still be shown as `0 cards | 0% done`. The codebase and tests already reflect this behavior. For users who organize content hierarchically, the parent entry can therefore look empty or unfinished even when the subtree contains substantial study material and meaningful progress.

**Expected future behavior**

Parent folders should communicate the real amount of study content and progress that exists under them, or clearly distinguish direct-folder values from nested-folder values. A folder that represents a large subtree should never look empty when that subtree is full of flashcards.

## 3. Sidebar labels do not keep folder names and completion information readable at normal widths

**Problem**

Folder labels currently combine the folder name, total card count, and completion percentage in a single line. When names are long, deeply nested, or numerous, important information becomes difficult to read in the available sidebar width. The percentage may technically exist in the label, but it is not reliably visible in day-to-day use. This makes the sidebar less useful precisely in the larger libraries where progress signals matter most.

**Expected future behavior**

Folder names and progress information should remain readable in common window sizes, including large folder libraries and long folder names. The user should be able to understand both what the folder is and how complete it is without depending on unusually wide layouts.

## 4. The app does not show elapsed active study time for the current session or cumulative study time overall

**Problem**

The timer page currently shows countdown state and scored-session progress, but it does not show how much time has actually been spent studying in the current session, nor how much time has been accumulated across sessions. This leaves a gap between the Pomodoro countdown and the user's real study effort. It also makes it hard to answer basic questions such as how long a session lasted or how much time was genuinely spent studying over time.

**Expected future behavior**

The app should expose both current-session active study time and cumulative study time in a way that reflects real studying activity rather than merely the app being open. Users should be able to understand how long they studied today and how much study time they have accumulated overall.

## 5. The active flashcard does not identify its source deck clearly enough

**Problem**

When the user studies from more than one folder, the timer page can fall back to a generic context such as multiple folders selected, but the currently visible flashcard does not tell the user which folder or deck it came from. At the data level, flashcards already preserve origin-related metadata, but that provenance is not surfaced as part of the studying experience. This weakens orientation during mixed-deck study sessions and makes it harder to understand where a card belongs.

**Expected future behavior**

During study and management workflows, the user should be able to identify the source deck or folder of a flashcard clearly and consistently. Mixed-folder sessions should preserve card provenance instead of hiding it behind a generic multi-folder context.

## 6. Audio settings do not provide in-app mute and volume control

**Problem**

The current sound settings focus on choosing, testing, and stopping notification sounds, but there is no app-level mute control and no way to adjust notification volume inside Estudai. That forces users to rely on system-wide audio controls even when they only want to change Estudai's behavior. For a study tool built around timed cues, this creates unnecessary friction in everyday use.

**Expected future behavior**

Estudai should let the user mute notification sounds and control their volume from inside the app. Audio behavior should be adjustable at the app level so that study cues can be tuned without affecting unrelated system audio.

## 7. The folder tree has no bulk select workflow for large libraries

**Problem**

Folder selection is currently optimized for individual checks and parent-to-descendant cascading, but there is no dedicated way to select all folders at once from the sidebar. This becomes increasingly impractical as the number of folders grows. The management table already has bulk-selection behavior for flashcards, so the folder tree feels comparatively slower and more repetitive for users with large libraries.

**Expected future behavior**

Users should be able to apply bulk selection to the folder tree quickly and predictably, including the common case of selecting the full library for study. Folder selection should remain practical even when the library grows very large.

## 8. Some inline LaTeX and scientific notation still render incorrectly in real study content

**Problem**

The current inline rendering path supports several common expressions and already has test coverage for simpler cases such as subscripts, superscripts, and Greek letters. Even so, the notes identify a real formatting problem with content like `$Na^+, K^+-ATPase$`. This suggests that the current rendering is good for many cases but still unreliable for some scientific and biomedical expressions that appear in actual flashcards. When that happens, the study material becomes harder to read exactly where precision matters most.

**Expected future behavior**

Inline LaTeX and scientific notation should render consistently and legibly across the kinds of expressions that users actually study. Scientific card content should preserve its intended meaning and visual structure in both question and answer views.

## 9. There is no calendar-based planning workflow for assigning study work to specific days

**Problem**

The current codebase contains timer, folder, flashcard, and progress flows, but no calendar or date-based planning surface. There is no way to assign folders to a given day, plan today's study set, or use the app as a study calendar. This leaves a large gap between doing a study session and deciding what should be studied on a given date.

**Expected future behavior**

The app should support date-based study planning, including assigning one or more folders to specific days. Users should be able to look at a day and understand what was planned for that day without leaving the app.

## 10. There is no built-in workflow for scheduling when completed material should be studied again

**Problem**

Although the app tracks flashcard progress, it does not currently let the user decide when a finished folder should be revisited or keep a day-level plan for future repetition. The notes describe a study rhythm in which finishing today's assigned material should naturally lead into choosing the next review date or interval. That entire scheduling loop is absent from the current product.

**Expected future behavior**

Once a planned study unit is completed, the app should let the user schedule when that same material should be reviewed again. Repeat planning should be part of the normal study flow rather than something the user has to track externally.

## 11. Daily study history does not expose effective study time per day

**Problem**

There is currently no daily history view that answers how much effective study time was completed on a given day. Because the app also lacks day-level study logs, the user cannot inspect a date and understand the real amount of study work performed on that date. This makes it difficult to connect study plans, actual execution, and historical effort.

**Expected future behavior**

The app should preserve day-level study history and show effective study time for each day. Users should be able to inspect a date and understand how much real studying happened on that day, not just whether the app was opened.

## 12. Creating the first flashcard in an empty folder can silently re-add that folder to active study selection

**Problem**

The current management workflow treats checked flashcard rows as the signal for whether a folder belongs in the active study scope. Newly added management rows start checked, and saving checked rows re-checks the edited folder. That means an empty folder that was not meant to be part of the current study scope can become selected again simply because the user added its first flashcard. Content editing and study-scope selection become coupled in a way that can surprise the user.

**Expected future behavior**

Creating or editing flashcards should not silently change whether a folder is part of the current study selection. A folder should enter or leave the active study scope only when the user explicitly chooses that change.

## 13. The study flow has forward skip but no backward navigation or rewind

**Problem**

The timer page exposes forward-oriented study controls, including skip, but the flow does not provide a corresponding way to move backward through recent flashcard history. The current sequencing logic is centered on advancing through the session rather than revisiting what just happened. This makes it difficult to recover from accidental skips or quickly revisit the immediately previous flashcard.

**Expected future behavior**

The study flow should support a clear backward-navigation path alongside the existing forward skip behavior. Users should be able to revisit recent study history without losing their orientation in the current session.

## 14. Global study statistics are persisted at flashcard level but not surfaced as a user-facing overview

**Problem**

The codebase already stores per-flashcard outcome information such as correct answers, wrong answers, and last reviewed timestamps, but those values are not turned into a global statistics view. As a result, the user cannot answer broader questions such as how many total hours were studied, how many responses were correct or wrong across the library, or how overall performance is evolving. Valuable study data exists but remains fragmented and hidden.

**Expected future behavior**

The app should provide a global statistics view that summarizes study activity and outcomes across folders and sessions. Users should be able to understand cumulative effort, response patterns, and high-level performance without inspecting individual flashcards one by one.

## Note already covered by the current codebase

The note about requiring the user to choose a target folder before importing a NotebookLM CSV does not need a new issue in the current state of the project. The import dialog already requires a target folder selection, and the import action stays unavailable when no valid target folder is selected.
