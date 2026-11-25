<!--
  SCREENSHOTS STILL TO TAKE (README → "Screenshots": mock mode, /admin/sign-in?as=mcvp,
  1280 × 720 window, PNG). Save them in images/02-people-and-memberships/ and add each
  one under the step named here. Use only the made-up people of the mock; never a real one.
    01-people-screen.png        The People screen with the mock people listed, showing the
                                Status and EXPA columns                                   → "The People screen"
    02-people-menu.png          The ⋮ menu of a person who is linked to EXPA (Edit, Manage
                                memberships, Unlink EXPA, Deactivate)                     → "The People screen"
    03-add-person.png           The Add person box, filled in with a made-up name and email → "Add a person", step 3
    04-edit-person.png          The Edit box for a person who is linked to EXPA, showing the note
                                about the email                                           → "Edit a name or email", step 3
    05-deactivate.png           The Deactivate box for a made-up person                   → "Deactivate a person", step 2
    06-memberships-screen.png   The Memberships screen with a person chosen and their
                                memberships listed (include one Current and one Ended)    → "The Memberships screen"
    07-assign.png               The Assign membership box, filled in                      → "Assign a membership", step 3
    08-transfer-warning.png     The Assign membership box with a different LC chosen for
                                someone who has a current membership, so the yellow
                                transfer message shows                                    → "Transfer someone to another LC"
    09-correct.png              The Correct membership box, with the End date changed     → "Correct a membership", step 3
    10-end.png                  The End membership box                                    → "End a membership early", step 3
    11-unlink.png               The Unlink EXPA box                                       → "Unlink an EXPA account", step 2
  Delete this comment once the screenshots are in.
-->

# 2. Adding people and memberships

**What this is for:** getting people into the tool and giving them access. You add a
person, then give them a **membership**: a position (and usually a function) in an LC for
a set period. You also use this to fix mistakes, move someone to another LC, end a
membership early, make a term longer, and stop someone signing in.

**Who can do this:** anyone on the MC, and anyone in an admin position. There is one extra
rule: you can only change people, and positions, that are **more junior than your own**,
and never your own record. See [Who you can and can't change](#who-you-can-and-cant-change).

**Where:** Admin console → **People** and Admin console → **Memberships**.

## Before you start

- **Nothing here deletes a person or their history.** Deactivating, ending and
  correcting all keep every past membership and KPI where it was. Ended memberships stay
  on the person as history.
- **A person can only sign in while they have a current membership.** Adding a person
  does not give them access. Assigning a membership does.
- Everything you do here is recorded in the audit log, with who did it and when.
- Use the person's **AIESEC email** (the one they sign in to EXPA with). It is how the
  tool recognises them the first time they sign in. See
  [Fix a wrong EXPA match](#fix-a-wrong-expa-match).

## The People screen

Click **People** in the menu on the left. You'll see everyone in the tool, including
people who have no current membership.

![The People screen](images/02-people-and-memberships/01-people-screen.png)

| Column | What it means |
|---|---|
| **First name**, **Last name**, **Email** | The person's details. The email is how they sign in. |
| **Status** | **Active**: they hold a role today. **No current role**: they can sign in once they have one, but have none now. **Deactivated**: they can't sign in. |
| **EXPA** | **Linked** once they have signed in with EXPA. **Not linked** until then. |

Type in **Search people** to find someone by name or email.

Every action for a person is in the **⋮** menu at the end of their row.

![The ⋮ menu for a person, showing Edit, Manage memberships, Unlink EXPA and Deactivate](images/02-people-and-memberships/02-people-menu.png)

| Menu item | What it does |
|---|---|
| **Edit** | Change their name or email. |
| **Manage memberships** | Opens the Memberships screen with this person chosen. (You only see it if your position lets you manage memberships.) |
| **Unlink EXPA** | Only shown for people who are **Linked**. |
| **Deactivate** or **Reactivate** | Shows **Reactivate** for a deactivated person, and **Deactivate** for everyone else. |

## Add a person

Use this for someone new to the tool.

1. Click **Add person** (top right).
2. Fill in **First name**, **Last name** and **AIESEC email**.
3. Click **Add person**.

   ![The Add person box, filled in](images/02-people-and-memberships/03-add-person.png)

**Check it worked:** the person appears in the list with the status **No current role**.

They can't sign in yet. Next, [assign them a membership](#assign-a-membership).

## Edit a name or email

Use this to fix a typo, or when someone's name or AIESEC email changes.

1. In the person's row, click **⋮**, then **Edit**.
2. Change the **First name**, **Last name** or **AIESEC email**.
3. Click **Save**.

   ![The Edit box for a person linked to EXPA, with the note about the email](images/02-people-and-memberships/04-edit-person.png)

**Read the note under the fields.**

- If the person is **not linked** to EXPA yet, changing the email changes which account
  can sign in as them.
- If the person is **linked**, changing the email does **not** change who signs in: their
  EXPA account stays attached to them. See [Fix a wrong EXPA match](#fix-a-wrong-expa-match).

## Deactivate a person

Use this when someone has left, or must stop signing in now. This is how a person is
"removed": they can't be deleted, because their history (memberships, KPIs, reports)
still points at them.

What happens:

- They **can't sign in**, and anywhere they are signed in is signed out.
- Their **current memberships end straight away** (yesterday, or today if one started
  today).
- Their **past memberships and KPI records stay**, so past reports don't change.
- Memberships that **haven't started yet are kept but don't count**. They don't give
  access, and the person doesn't appear as a member, until you reactivate them.

1. In the person's row, click **⋮**, then **Deactivate**.
2. Read the message and click **Deactivate**.

   ![The Deactivate box, explaining that memberships end straight away and nothing is deleted](images/02-people-and-memberships/05-deactivate.png)

**Check it worked:** the Status shows **Deactivated**.

You can't deactivate yourself.

### Undo: reactivate a person

1. In the person's row, click **⋮**, then **Reactivate**.
2. Click **Reactivate**.

What comes back, and what doesn't:

- They can sign in again **once they have a current membership**.
- **Memberships that ended because of the deactivation stay ended.** Assign a new one on
  the Memberships screen.
- **Their status becomes Active**, even if they were an alumnus before. Change it back
  if that matters.
- Memberships that hadn't started yet when you deactivated them count again.

## The Memberships screen

Click **Memberships** in the menu on the left, or choose **Manage memberships** from a
person's **⋮** menu on the People screen.

1. Under **Person**, search by name or email and choose the person.

   ![The Memberships screen, with a person chosen and their memberships listed](images/02-people-and-memberships/06-memberships-screen.png)

You'll see every membership they have ever had:

| Column | What it means |
|---|---|
| **LC**, **Position**, **Function** | Where and as what. |
| **Team** | The team they are in, if any. |
| **Term** | The term the membership belongs to. |
| **Start**, **End** | The dates, as day/month/year. |
| **Status** | **Current** (running today), **Upcoming** (starts later) or **Ended**. |

Each membership has a **⋮** menu with **Correct**, and **End** (hidden once it has ended).

If the person is deactivated, the screen says so and **Assign membership** is switched
off. Reactivate them on the People screen first.

## Assign a membership

Use this to give a person access, or to add a new role.

1. Choose the person, then click **Assign membership**.
2. Choose the **LC**, then the **Position**, then the **Function**. Each list depends on
   the one before: the positions offered fit the LC (an LC position for an LC, an MC
   position for the MC).
3. Set the **Start date** and **End date**. Both are needed. The end date is usually the
   end of their term.
4. Click **Assign**.

   ![The Assign membership box, filled in](images/02-people-and-memberships/07-assign.png)

**Check it worked:** the membership appears in the person's list as **Current** (or
**Upcoming** if it starts later).

### Transfer someone to another LC

A transfer is just an assignment to a **different** LC from the one the person is in now.
When you choose the other LC, a yellow message appears:

![The Assign membership box with the transfer message](images/02-people-and-memberships/08-transfer-warning.png)

> This is a transfer. Their memberships in other LCs end the day before this one starts.
> Their past records stay with those LCs.

So nothing is lost: the old LC keeps its history, and the new membership starts the next
day. Click **Assign** to go ahead.

**Any Assign is refused if the person already has a membership in another LC that hasn't
started yet and overlaps these dates.** Otherwise the tool would have to cancel a
membership that hasn't begun.
The message names the LC and the start date. Correct or end that membership first (see
below), then assign again.

## Correct a membership

Use this to fix a **mistake**: the wrong position, function or date. It changes the
membership in place, and the audit log keeps what it was before.

> **If someone's role really changed**, don't correct it. End the old membership and
> assign a new one, so their history shows what happened.

1. Choose the person. On the membership's row, click **⋮**, then **Correct**.
2. Change the **Position**, **Function**, **Start date** or **End date**.
3. Click **Save correction**. The button only works once something has changed.

   ![The Correct membership box, with the End date changed](images/02-people-and-memberships/09-correct.png)

Things you can't change here:

- **The LC.** Moving someone to another LC is a [transfer](#transfer-someone-to-another-lc).
- **The function, once they have been in a team.** The team belongs to the old function.
  End the membership and assign a new one.

### Extend a term

To make a membership last longer, correct its **End date**: choose **Correct**, set a
later **End date** and click **Save correction**. **End** can only make a membership
shorter.

### Moving a start date

If you move the **Start date** later, the person's time in teams moves with it, so they
are never in a team before they have a membership. If a team period would end up empty
(it ended before the new start date), the correction is refused. Choose an earlier start
date, or end the membership and assign a new one.

## End a membership early

Use this when someone leaves their role before their term was due to end.

1. Choose the person. On the membership's row, click **⋮**, then **End**.
2. Check the role and LC in the message, and set the **End date**. It starts as today.
3. Click **End membership**.

   ![The End membership box](images/02-people-and-memberships/10-end.png)

They keep access up to and including the end date. The membership, its history and KPI
records stay. If they were in a team, their time in it ends on the same date.

**Check it worked:** the membership's status shows **Ended** once the date has passed.

## Unlink an EXPA account

A person is **Linked** once they have signed in with EXPA. The tool then recognises them
by their EXPA account from then on, whatever email they use.

**Unlinking does not undo a wrong match on its own.** The next time anyone signs in with
EXPA using this person's AIESEC email, that account is linked again. That is how a wrong
match happens in the first place. To fix one, [correct the email first](#fix-a-wrong-expa-match).

What unlinking does: it clears the link and **signs the person out everywhere**. Nothing
else changes: their memberships and history stay.

1. In the person's row, click **⋮**, then **Unlink EXPA**. (It's only there for people
   who are **Linked**.)
2. Read the message and click **Unlink**.

   ![The Unlink EXPA box](images/02-people-and-memberships/11-unlink.png)

**Check it worked:** the EXPA column shows **Not linked**. You can't unlink yourself.

### Fix a wrong EXPA match

Use this if someone signs in and sees another person's details, or an EXPA account was
linked to the wrong person.

1. On the **wrongly matched** person's record, click **⋮**, then **Edit**. Correct their
   **AIESEC email** (so it no longer matches the wrong EXPA account) and save.
2. On that **same** record, click **⋮**, then **Unlink EXPA**, and click **Unlink**.
3. The right owner of that email signs in with EXPA. They are linked to this record by
   their AIESEC email.

Do the email first. If you unlink first, the next sign-in with the old email links the
wrong account again.

## Who you can and can't change

- **Not yourself.** You can fix your own name and email, but you can't deactivate or
  unlink yourself, or change your own memberships.
- **Only people junior to you.** You can't change someone who holds a position at or
  above your own, or who is about to (a membership that hasn't started yet counts).
  Ask someone more senior.
- **Only positions junior to yours.** You can't assign a position at or above your own.

## If something goes wrong

| You see | What it means | What to do |
|---|---|---|
| "Use an AIESEC email address." | The email isn't from an allowed AIESEC domain (the allowed domains are set per environment). | Use the person's AIESEC email. |
| "Enter a valid email address." | The email isn't written as an email address. | Check for typos. |
| "Someone already has that email address." | Another person in the tool has that email. | Find them with **Search people**. Don't add a second record for the same person. |
| "Enter a first name and a last name." | A name was left empty. | Fill in both. |
| "You can't do this to your own record." | You tried to deactivate or unlink yourself. | Ask another admin. |
| "This person is already deactivated." | They were deactivated already. | Nothing to do. |
| "Only a deactivated person can be reactivated." | The person isn't deactivated. | Nothing to do. |
| "This person isn't linked to EXPA." | There is no link to remove. | Nothing to do. |
| "Reactivate this person before assigning a membership." | They are deactivated. | Reactivate them on the People screen first. |
| "That LC is inactive." | The LC has been closed. | Choose another LC, or mark it active (guide 1). |
| "The end date must be on or after the start date." | The dates are the wrong way round. | Fix the dates. |
| "… can't be used in an LC." / "… can't be used in the MC." | The position belongs to the other kind of committee. | Choose a position that fits the LC. |
| "You can't assign or change a position at or above your own." | The position is as senior as yours or more. | Ask someone more senior. |
| "You can't change your own memberships." | You are the person. | Ask another admin. |
| "This person's membership in (LC) starts on (date). Correct it first, or end this one before that date." | They already have an upcoming membership in another LC. | Correct or end that membership first, then try again. |
| "This person already holds that function in this LC for overlapping dates." | They already have that function in that LC at the same time. | Correct or end the other membership, or choose different dates. |
| "This person can't be added. Contact your MC." | An LC membership can't overlap an MC one. | Change the dates, or end the MC membership first. |
| "No term covers that start date." | No term has been set up for that date. | Choose a start date inside a term. |
| "These dates overlap this person's membership in another LC. Correct or end that one first." | A correction would clash with their membership elsewhere. | Correct or end the other one first. |
| "This membership has been in a team of its current function. End it and assign a new one instead, so the team history stays right." | You tried to change the function after a team. | End it and assign a new one. |
| "A team row of this membership ended before that start date. Choose an earlier start date, or end this membership and assign a new one." | The new start date is after a team period already finished. | Choose an earlier date, or end and assign a new one. |
| "A membership can't end before it started." | The end date is before the start date. | Choose a later date. |
| "Choose a date before the current end date. To extend, use Correct." | **End** can only shorten a membership. | To make it longer, use **Correct**. |
| No **⋮** menus, or no **Add person** button | Your position doesn't give you permission. | Ask someone on the MC. |

## Related guides

- [1. Managing LCs](01-managing-lcs.md): adding the LC before you add people to it.
- Guide 3, term handover (not written yet): adding the next team at the end of a term.
- Guide 7, reading the audit log (not written yet): seeing who changed what and when.
