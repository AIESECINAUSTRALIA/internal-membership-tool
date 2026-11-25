<!--
  SCREENSHOTS STILL TO TAKE (README → "Screenshots": mock mode, /admin/sign-in?as=mcvp,
  1280 × 720 window, PNG). Save them in images/05-kpis-functions-positions/ and add each
  one under the step named here:
    01-screen.png             The Positions & functions screen (both tables)          → "The Positions & functions screen"
    02-add-position.png       Add position box, filled in: Coordinator, LC, rank 2   → "Add a position", step 5
    03-position-menu.png      The ⋮ menu for LC President                             → "The Positions & functions screen"
    04-edit-details.png       "Edit details: …" box (⋮ → Edit rank / level)                        → "Change a position's level, rank or president rule", step 3
    05-deactivate.png         Deactivate box for a position                           → "Deactivate a position", step 2
    06-add-function.png       Add function box, with a name typed in                  → "Add a function", step 3
  Delete this comment once the screenshots are in.
-->

# 5. Adding or retiring a KPI, function or position

**What this is for:** keeping the lists people choose from up to date. Add a new
position or function when the national structure changes, fix a name, or retire one
that is no longer used, without losing anyone's history.

**Who can do this:** anyone on the MC, and anyone in an admin position. For positions
there is one extra rule: you can only change positions that are **more junior than your
own** (see [Who can change which position](#who-can-change-which-position)).

**Where:** Admin console → **Positions & functions**. KPIs are on a different screen:
see [KPIs](#kpis).

## Before you start

- **Nothing on this screen deletes anything or changes anyone's history.** Renaming and
  deactivating both keep every past and current membership exactly as it was.
- **A new position can't do anything yet.** What a position is allowed to see and change
  is set in the permission matrix, which isn't on the Admin console yet. After adding a
  position, ask the tech team to give it permissions. Until they do, people in that
  position can sign in but can't see anyone's data.
- **Every change can be reversed** from this screen, and every change is recorded in the
  audit log, with who did it and when.

## Words used on this screen

| Word | What it means |
|---|---|
| **Position** | A person's role, like Member, Team Leader, LCVP or LCP. |
| **Function** | The area someone works in, like oGV, Finance or Talent Management. |
| **Level** | Whether the position belongs to an **LC** or to the **MC**. An LC position can only be given in an LC, and an MC position only in the MC. |
| **Rank** | How senior the position is. **A higher number is more senior**: Member is 1, Team Leader 2, LCVP 3, LCP 4, MCD 5, MCVP 6, MCP 7. People can only add or manage people in positions ranked below their own. |
| **Can add same rank** | The president rule: an LCP can add another LCP (for example, a co-president), even though they have the same rank. Only presidents have this. |
| **Key** | A short code the tool uses behind the scenes. It is made from the first name you give and never changes, even if you rename. You don't need to do anything with it. |

## The Positions & functions screen

Click **Positions & functions** in the menu on the left. Positions are listed first,
most senior at the top. Functions are below, in alphabetical order.

Every action for an existing position or function is in the **⋮** menu at the end of its
row.

### Who can change which position

You can only change a position that ranks **below your own**, and you can only give a
position a rank below your own. Positions at or above your rank have no **⋮** menu. For
example, an MCVP (rank 6) can change every LC position and the MCD, but not the MCVP or
MCP positions.

This stops anyone making a position more senior than themselves. If a senior position
needs changing, ask someone who ranks above it. Nobody ranks above the MCP, so the MCP
position can't be changed on this screen at all: ask the tech team.

## Add a position

1. Under **Positions**, click **Add position**.
2. Type the position's **Name**. It must be different from every other position,
   including inactive ones. Upper and lower case count as the same, so "Member" and
   "member" clash.
3. Choose its **Level**: **LC** or **MC**.
4. Type its **Rank**. The box tells you the highest rank you can give.
5. Tick **People in this position can add another person to the same position** only
   for a president-type position.
6. Click **Add position**.

**Check it worked:** the new position appears in the list as **Active**, in rank order.

Then ask the tech team to give it permissions (see [Before you start](#before-you-start)).

## Rename a position

Use this to fix a typo or when a role's name changes. Every screen shows the new name
straight away, including for past terms.

1. In the position's row, click **⋮**, then **Rename**.
2. Change the **Name**.
3. Click **Rename**.

## Change a position's level, rank or president rule

Changing a rank changes who can manage whom, so check with the MC before you do it.

1. In the position's row, click **⋮**, then **Edit rank / level**.
2. Change the **Level**, the **Rank**, or the president tick box.
3. Click **Save**.

Level and rank can be changed but not left empty.

## Deactivate a position

Use this when a position is no longer used. It can't be deleted, because past
memberships still point at it.

What changes: the position is no longer offered when someone adds a person.

What doesn't change: everyone who already holds it keeps it. **Deactivating a position
doesn't end anyone's membership.**

**MC positions can't be deactivated here.** They are what gives people access to this
Admin console, so deactivating one could lock every admin out. If an MC position really
needs to be retired, ask the tech team.

1. In the position's row, click **⋮**, then **Deactivate**.
2. Read the message and click **Deactivate**.

**Check it worked:** the position's status shows **Inactive**.

**Undo:** click **⋮**, then **Reactivate**, and confirm.

## Add a function

1. Under **Functions**, click **Add function**.
2. Type the function's **Name**. It must be different from every other function,
   ignoring upper and lower case.
3. Click **Add function**.

**Check it worked:** the new function appears in the list as **Active**, and is offered
when adding a person.

## Rename a function

1. In the function's row, click **⋮**, then **Rename**.
2. Change the **Name**.
3. Click **Rename**.

## Deactivate a function

What changes: the function is no longer offered when someone adds a person.

What doesn't change: everyone who already has it keeps it, and so do teams and KPIs.

1. In the function's row, click **⋮**, then **Deactivate**.
2. Read the message and click **Deactivate**.

**Undo:** click **⋮**, then **Reactivate**, and confirm.

## KPIs

Not written yet. KPIs are managed on the **Metrics & custom fields** screen; this part of
the guide will cover adding and retiring them.

## If something goes wrong

| You see | What it means | What to do |
|---|---|---|
| "A position with that name already exists" or "A function with that name already exists" | Another one, possibly inactive, already has that name (ignoring upper and lower case). | Choose a different name. If the other one is an inactive copy, reactivate it instead of adding a new one. |
| "You can only change positions ranked below your own" | The position, or the rank you chose, is at or above your own rank. | Choose a lower rank, or ask someone more senior to make the change. |
| "This position gives admin access, so it can't be deactivated here" | It's an MC or admin position. | Ask the tech team. |
| No **⋮** menu on a position | That position ranks at or above yours. | Ask someone more senior. |
| No **Add position** or **Add function** button | Your position doesn't give you permission to manage them. | Ask someone on the MC. |
| People in a new position can't see anything | The position has no permissions yet. | Ask the tech team to add it to the permission matrix. |

## Related guides

- [1. Managing LCs](01-managing-lcs.md): the same kind of screen, for LCs.
- Guide 4, changing permissions (not written yet): giving a new position what it needs.
- Guide 7, reading the audit log (not written yet): seeing who changed a position and when.
