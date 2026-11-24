# Admin guide

Step-by-step guides for the people who run the Membership Tool's **Admin console**.

You don't need to be technical, and you don't need anyone to explain the tool to you
first. Each guide says who can do the task, what to do click by click, and how to check
it worked. If a guide is unclear or a screen looks different from its screenshots, that
is a bug in the guide: tell the tech team so they can fix it.

> **Developers:** these guides are for admins. Design decisions and the database belong
> in the developer docs (`docs/`, e.g. `docs/data-model.md`), not here.

---

## Getting into the Admin console

The Admin console is a separate part of the Membership Tool with its own sign-in page.
Normal users never see a link to it.

1. Go to the Admin console address: the Membership Tool's address followed by
   `/admin/sign-in`.
2. Sign in with your AIESEC account.
3. You only get in if your **position** gives you admin access (for example, a position
   on the MC). Access is never given to a named person, and it ends when your term ends.

If you can't get in and you think you should, see guide 9 (recovering admin access).

## The guides

Spec §10A lists the guides every admin needs. A guide is written when its screen is
built, in the same piece of work, so a guide marked "not written yet" is waiting for its
screen.

| # | Guide | Status |
|---|---|---|
| 1 | [Managing LCs](01-managing-lcs.md): add, rename, set state, mark inactive, merge | Written |
| 2 | Adding people and memberships, with start/end dates, and extending a term | Not written yet: the Memberships screen isn't built |
| 3 | Term handover: who adds whom | Not written yet: needs the Memberships screen |
| 4 | Changing permissions, and the "you can't grant what you don't hold" rule | Not written yet: the Permission matrix screen isn't built |
| 5 | Adding or retiring a KPI, function or position | Not written yet: the Metrics & custom fields screen exists, so the KPI part can be written now |
| 6 | Processing a deletion request (the manual procedure for now) | Not written yet |
| 7 | Reading the audit log | Not written yet: the Auditing screen isn't built |
| 8 | Restoring from a backup | Not written yet: comes with the deployment work |
| 9 | Recovering admin access if every admin is locked out | Not written yet: comes with the admin lockout recovery ticket |
| 10 | Who holds which accounts (at least two people each), without secrets | Not written yet |

---

## Writing or updating a guide

These rules keep the guides usable by someone with no context, years from now.

### When

- **Any change to an admin screen updates its guide in the same pull request.** A new
  screen gets a new guide in the same pull request. The PR template has a checkbox for
  this.
- **At every handover**, the outgoing and incoming admins go through the guides together
  and fix anything that's unclear or out of date.
- **Someone who didn't build the feature reviews the guide.** Ideally someone
  non-technical. If they have to ask a question, the answer belongs in the guide.

### How

- Start from [`_template.md`](_template.md). Name the file with the guide's number and a
  short name: `05-managing-kpis.md`. Add it to the table above.
- **Plain language.** Write for an admin, not a developer. Say "LC", "member", "term";
  avoid words like "endpoint", "record", "row", "database" or "API". Explain any word
  the admin wouldn't use themselves.
- **Numbered steps**, one action each, using the exact words on the screen in **bold**
  ("Click **Add LC**").
- **A screenshot for each step that changes what's on screen.** Don't add one for every
  click.
- **Say what can't be undone**, in a warning before the step that does it.
- **Who can do this** names positions ("anyone on the MC"), never a person.
- **No code or SQL** for routine tasks. If a task seems to need it, the screen is missing
  something: raise it with the tech team instead of documenting a workaround.
- **Never include** passwords, keys, links that sign you in, or anyone's real personal
  data.

### The exception: emergency procedures

Guides 8 (restoring from a backup) and 9 (recovering admin access) cover situations
where the Admin console itself can't help, so they may include a command to copy and
paste. When they do:

- Put the command in its own box, on its own, under a heading that says what it does.
- Say exactly what to change in it (in `CAPITALS`), and that everything else must be
  copied exactly.
- Say who is allowed to run it and where (which account, which screen).
- Say how to check it worked, and what to do if it didn't.

### Screenshots

Screenshots must never show real people's data. Take them from the tool's **mock
mode**, where every person and number is made up:

1. Start the frontend in mock mode (`docs/local-development.md`, `docs/frontend.md`).
2. Open `/admin/sign-in?as=mcvp` and click **Sign in**. This signs in as a made-up MC
   member with admin access. Mock data resets when you reload the page, so move around
   by clicking, not by typing addresses.
3. Use a browser window of about 1280 × 720 and capture the whole window, so every
   screenshot looks the same.
4. Save them as PNG in `images/<guide file name>/`, numbered in the order the guide uses
   them: `images/01-managing-lcs/03-lc-added.png`.

Retake the screenshots when the screen changes. An out-of-date screenshot is worse than
none, because it makes the reader think they're in the wrong place.
