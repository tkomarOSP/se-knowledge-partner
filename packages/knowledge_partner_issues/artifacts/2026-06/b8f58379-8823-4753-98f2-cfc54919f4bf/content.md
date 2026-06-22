# SE Knowledge Partner — Tooling Issues Log

Persistent record of observed issues, workarounds, and resolutions with Knowledge Partner MCP tooling.

---

## 2026-06-11T11:16:42Z — issue

## ISSUE-001 · Binary file upload to artifact repo

**Tool:** artifact_repo  
**Status:** Open  
**System Prompt Ref:** [f6965579]  
**First observed:** 2026-06-10, Road Grader Front Axle Assembly session

### Description
Binary files (PNG, PDF, etc.) cannot be committed to the artifact repository. Attempting to store a binary deliverable results in failure — the file remains local only.

### Impact
CAD images, generated PDFs, and other binary deliverables produced during a session cannot be persisted to the shared knowledge repo. Only text/Markdown reference artifacts can be created as a substitute.

### Workaround
Create a `text` artifact that documents the binary file's content, component inventory, and engineering observations. Note the limitation and local file location explicitly in the artifact. Reference open issue ID in the artifact text.

### Suggested Fix
Add base64-encoded binary support to `write_artifact`, or support a separate `upload_binary` tool that stores files in a designated `/assets` path in the repo.

---

## 2026-06-11T11:16:51Z — issue

## ISSUE-002 · Author identity not captured on commits

**Tool:** capella-fabric (`apply_model_patch`), artifact_repo (`write_artifact`, `add_log_entry`)  
**Status:** Open  
**System Prompt Ref:** [b1699e70]  
**First observed:** 2026-06-10, Road Grader Front Axle Assembly session

### Description
Neither `apply_model_patch` nor artifact write/push operations accept an `author_name` or `author_email` parameter. All commits are attributed to the service account identity rather than the engineer performing the work.

### Impact
Git history does not reflect who made each change. Traceability and accountability are reduced, particularly in multi-user or audited environments.

### Workaround
Embed `[Author Name]` explicitly in every `commit_message` string. Example: `"[SE Knowledge Partner] Add missing description to Structural load bearing capability"`. This preserves intent in the commit message even though the git author field is incorrect.

### Suggested Fix
Add optional `author_name` and `author_email` parameters to `apply_model_patch`, `write_artifact`, and `push_artifacts`. Apply as the git committer identity when provided.

---

## 2026-06-11T11:17:01Z — issue

## ISSUE-003 · `create_artifact_branch` returns "No approval received"

**Tool:** artifact_repo (`create_artifact_branch`)  
**Status:** Open  
**First observed:** 2026-06-10, Road Grader Front Axle Assembly session

### Description
Calling `create_artifact_branch` to create a new `main` branch on a fresh repository returned `"error: No approval received"` and did not create the branch. The call used `push_upstream: true`.

### Reproduction
1. Clone a repo that only has a `master` branch
2. Call `create_artifact_branch` with `branch_name: "main"` and `push_upstream: true`
3. Result: `"No approval received"`

### Impact
Cannot initialize a separate `main` artifact branch on repos that don't already have one. The system prompt convention (model changes on `master`, artifacts on `main`) cannot be implemented for new repos via tooling alone — requires manual branch creation on GitHub first.

### Workaround
Write artifacts directly to `master` branch. Note the branch limitation in the work log. Request engineer to manually create `main` branch on GitHub if the convention needs to be enforced.

### Suggested Fix
Clarify what "approval" mechanism is required and whether it is a permissions issue, a missing parameter, or a tool bug. Add appropriate error messaging that distinguishes permission denial from a missing parameter.

---

## 2026-06-11T11:17:12Z — issue

## ISSUE-004 · Artifact session push rejected after model patch advances shared branch HEAD

**Tool:** artifact_repo (`push_artifacts`), capella-fabric (`push_model_changes`)  
**Status:** Open  
**First observed:** 2026-06-10, Road Grader Front Axle Assembly session

### Description
When both a capella-fabric session and an artifact_repo session are open simultaneously and cloned from the same repository branch (`master`), pushing model changes via `push_model_changes` advances the remote HEAD. A subsequent `push_artifacts` call from the artifact session (which was cloned at the earlier HEAD) is then rejected with a non-fast-forward error.

### Error
```
! [rejected] master -> master (fetch first)
error: failed to push some refs — remote contains work not in local
```

### Impact
Artifact log entries written during the same session as model patches may fail to push. Requires session cleanup and re-clone of the artifact session to recover, causing extra round-trips and risk of losing in-flight log entries if not handled carefully.

### Workaround
1. Always push model changes (`push_model_changes`) before writing artifact log entries in the same session.
2. If rejection occurs: cleanup artifact session, re-clone, re-add log entries, then push.
3. Consider serializing operations — complete all model patches and push, then open a fresh artifact session for logging.

### Suggested Fix
Implement a `git pull --rebase` before push in `push_artifacts` to handle non-fast-forward situations gracefully, provided there are no conflicting changes to the same files.

---

## 2026-06-11T11:17:23Z — issue

## ISSUE-005 · `search_model_objects` silently requires `phase` and `object_type` — validation error on omission

**Tool:** capella-fabric (`search_model_objects`)  
**Status:** Open  
**First observed:** 2026-06-10, Road Grader Front Axle Assembly session

### Description
Calling `search_model_objects` without `phase` and `object_type` parameters returns a Pydantic validation error rather than a helpful message or a cross-phase search result. The error is not surfaced clearly as a missing parameter issue without reading the raw error text.

### Error
```
2 validation errors for search_model_objectsArguments
phase: Field required
object_type: Field required
```

### Impact
Cross-phase name searches (e.g. "find all objects named 'Grader' anywhere in the model") are not possible with a single call. Each search requires knowing the phase and object type in advance, increasing the number of calls needed to locate objects of unknown type or layer.

### Workaround
Always supply both `phase` and `object_type` when calling `search_model_objects`. When object type or layer is unknown, iterate across phases (OA/SA/LA/PA) and relevant object types explicitly.

### Suggested Fix
Either (a) make `phase` and `object_type` optional with a cross-phase fallback search, or (b) improve the error message to clearly state which parameters are missing rather than surfacing raw Pydantic validation output.

---

## 2026-06-11T11:17:35Z — issue

## ISSUE-006 · Capability actor involvement attribute name not discoverable without fabric generation

**Tool:** capella-fabric (`apply_model_patch`)  
**Status:** Open  
**First observed:** 2026-06-10, Road Grader Front Axle Assembly session

### Description
When patching actor involvements on a `Capability` object, the correct `extend:` attribute name is `involved_components`. Two incorrect attribute names were attempted first — `involved_elements` and `involved actors` (with space) — both returning errors before the correct name was found by inspecting the generated fabric YAML.

### Errors encountered
```
'Capability' object has no attribute 'involved_elements'
'Capability' object has no attribute 'involved actors'
```

### Resolution
Correct attribute name confirmed via `generate_fabric` output, which showed `involved actors:` as a display label in the YAML — but the actual patch attribute is `involved_components`.

### Impact
Multiple failed patch attempts required per operation when working with less common Capability attributes. Increases token usage and session time. Risk of applying incorrect patch if error not caught.

### Workaround
Always run `generate_fabric` before patching Capability involvement relationships to confirm the correct attribute name from the fabric YAML. Do not rely on display labels in fabric output as literal patch attribute names.

### Suggested Fix
Document the mapping between fabric YAML display labels and patch attribute names. Alternatively, improve error messages to suggest the correct attribute name when a close match exists (e.g. "did you mean `involved_components`?"). Consider adding a `describe_object_schema` tool that returns patchable attribute names for a given object type.

---

## 2026-06-11T12:34:48Z — issue

## ISSUE-007 · Duplicate UUID in model fragment blocks all capella-fabric operations

**Tool:** capella-fabric (all tools)
**Status:** Open — requires engineer action in Capella
**First observed:** 2026-06-11, Road Grader Front Axle Assembly session
**Blocking:** Yes — no browse, search, verify, patch, or fabric generation possible until resolved

### Description
All capella-fabric operations against the Road Grader Front Axle Assembly model return the following error:

```
Duplicate UUID 'c1d22496-a4f3-4fa9-888c-1cbee21d4adb' within fragment Road_Grader_Front_Axel_Assembly.capella
```

This affects `browse_model`, `search_model_objects`, `verify_model`, `generate_fabric`, and `apply_model_patch`. The model is completely unqueryable until the duplicate is resolved.

### Likely Cause
A copy/paste or drag-and-drop operation in Capella duplicated an element without generating a new UUID for it. This most likely occurred when adding new actors or components to the [SAB] Road Grader Context View diagram shortly before this session.

### Resolution Steps (engineer action required in Capella)
1. Open the model in Capella
2. Go to **Window → Preferences → Capella → Model Validation** or use **Right-click on model root → Validate**
3. Run model validation — it will flag the duplicate UUID element
4. Identify the duplicate element (UUID: `c1d22496-a4f3-4fa9-888c-1cbee21d4adb`)
5. Delete the duplicate element (keep the original)
6. Save the model and commit/push to master
7. Notify Knowledge Partner to re-clone and resume

### Alternative Resolution (advanced)
Open `Road_Grader_Front_Axel_Assembly.capella` in a text editor, search for all occurrences of `c1d22496-a4f3-4fa9-888c-1cbee21d4adb`, identify the duplicate entry, and remove it. Save, commit, and push.

### Impact
All Knowledge Partner model operations are blocked. No functions, components, or patches can be applied until resolved.

---

## 2026-06-11T13:15:49Z — issue

## ISSUE-008 · Functions created via extend under SystemFunction parent typed as LogicalFunction — blocks actor allocation

**Tool:** capella-fabric (`apply_model_patch`)
**Status:** Open
**First observed:** 2026-06-11, Road Grader Front Axle Assembly — SA Functions session
**Blocking:** Partial — functions created correctly but cannot be allocated to actors

### Description
When extending a `SystemFunction` (e.g. `Root System Function`) with child `functions:`, capellambse creates the new functions as `LogicalFunction` type instead of `SystemFunction`. This causes the subsequent `allocated_functions` patch on `SystemComponent` actors to fail with a type mismatch error.

### Error
```
Cannot insert into SystemComponent.allocated_functions: Objects must be instances of
org.polarsys.capella.core.data.ctx:SystemFunction,
not <class 'capellambse.metamodel.la.LogicalFunction'>
```

### Reproduction
1. Extend a `SystemFunction` (SA phase) with `functions:` containing new named child functions
2. Browse the model — new functions show as `LogicalFunction` type with `layer: LA`
3. Attempt to allocate via `extend: allocated_functions: [!uuid <function-uuid>]` on a `SystemComponent`
4. Result: type mismatch error

### Impact
Actor function allocation cannot be completed via patch. Engineer must manually allocate actor functions to their respective actor components in Capella. Affects all SA actor function creation workflows.

### Workaround
Create functions via patch (they land in the model correctly despite wrong type label), then manually allocate them to actors in Capella using drag-and-drop or the Capella allocation dialog. Commit and push after manual step.

### Suggested Fix
Investigate whether capellambse `extend: functions:` under a `SystemFunction` parent should resolve to `SystemFunction` type. May require explicit `type: SystemFunction` parameter in the patch YAML, or a fix in the capella-fabric patch handler to infer correct function type from parent layer context.

---

## 2026-06-11T13:31:54Z — observation

## OBS-001 · Engineer commit discipline required for agent/model synchronization

**Source:** Road Grader Front Axle Assembly modeling session, 2026-06-11
**Category:** Workflow — human/agent collaboration

### Observation
The Knowledge Partner agent operates against a GitHub-hosted copy of the Capella model. For the agent to see engineer-made changes (e.g. manually added capabilities, function allocations, diagram edits), the engineer must save the model in Capella and commit and push to the remote branch before the agent re-clones. This is a deliberate synchronization boundary — the agent always works from the committed state, not the local working copy.

### Effort assessment
This does require discipline and adds friction compared to a fully integrated tool. However, the engineer assessed this as acceptable overhead, particularly if the solution is open-sourced. The commit-before-agent-use pattern is a known and well-understood workflow in developer tooling (e.g. CI/CD pipelines, code review agents), and systems engineers can adapt to it.

### Mitigating factor — OBEO integration roadmap
OBEO (the commercial steward of Capella) is planning a tighter integration with this workflow pattern. A native integration would eliminate the manual commit step by allowing the agent to interface directly with the Capella model server or a live repository sync, significantly reducing the friction observed here.

### Recommendation
Document the commit-before-agent-use requirement explicitly in onboarding materials for new users of this workflow. Consider a lightweight checklist or reminder in the Knowledge Partner system prompt.

---

## 2026-06-11T13:32:11Z — observation

## OBS-002 · Frequent commits as a model integrity safety net — git history enables rapid rollback

**Source:** Road Grader Front Axle Assembly modeling session, 2026-06-11
**Category:** Workflow benefit — model integrity and recovery

### Observation
The Knowledge Partner workflow pattern of committing model changes frequently — both agent-applied patches and engineer-applied edits — provides a meaningful model integrity safety net. This was demonstrated directly during the Road Grader session when a duplicate UUID (c1d22496-a4f3-4fa9-888c-1cbee21d4adb) was introduced into the model, blocking all capella-fabric operations.

### How it helped
Because the model was under continuous git version control with frequent small commits, the engineer was able to:
1. Identify that the model was in a broken state (agent reported the duplicate UUID error)
2. Locate the last known-good commit in git history
3. Revert to that commit
4. Recreate only the small amount of work performed since that commit (the [SAB] Context Diagram)

The total rework was minimal — estimated at less than 30 minutes of effort. Without git version control, detecting and recovering from a corrupt model state could require hours of manual XML inspection or full model reconstruction.

### Root cause of the duplicate UUID
The exact cause was not determined. Likely candidates include a copy/paste operation in Capella that duplicated an element without generating a new UUID, or a drag operation that created a reference with a conflicting identifier. This is a known risk in Capella model editing.

### Broader implication
Frequent, granular commits are a best practice that this workflow naturally encourages. Each agent patch is a discrete commit with a descriptive message, and engineer manual edits should follow the same discipline. The git history serves as both an audit trail and a recovery mechanism — two benefits that are underappreciated in traditional MBSE workflows where model files are often stored without version control or with infrequent checkpoints.

### Recommendation
Treat every modeling session as a series of small, committed increments rather than large batch saves. The overhead is low and the recovery value is high. This practice should be highlighted as a key benefit in any evaluation or open-source documentation of the Knowledge Partner workflow.

---

## 2026-06-11T14:18:09Z — issue

## ISSUE-009 · Functions created in SA layer via patch are typed as LogicalFunction instead of SystemFunction — incorrect metamodel type

**Tool:** capella-fabric (`apply_model_patch`)
**Status:** Open — model correction required
**First observed:** 2026-06-11, Road Grader Front Axle Assembly — [SAB] CAP-01 Steering Control review
**Related:** ISSUE-008 (allocation failure was a symptom of this same root cause)
**Severity:** High — incorrect metamodel typing pollutes the SA layer and will cause issues at LA/PA decomposition and traceability

### Description
When `apply_model_patch` is used to create functions via `extend: functions:` under a `SystemFunction` parent (e.g. `Root System Function` in the SA layer), capellambse creates the child functions as `LogicalFunction` type (from `org.polarsys.capella.core.data.la`) instead of `SystemFunction` type (from `org.polarsys.capella.core.data.ctx`).

This means all 17 functions created during the Road Grader SA session — 8 system functions and 9 actor functions — are typed as `LogicalFunction` in the underlying `.capella` XML, despite appearing in the SA layer. The fabric confirms this with `type: LogicalFunction` and `layer: LA` on all created functions.

### Visible symptom
In Capella, the SA function tree shows `LogicalFunction` icons instead of `SystemFunction` icons. Functions appear in the System Analysis view but carry the wrong metamodel type. This was observed directly by the engineer during the [SAB] CAP-01 review session.

### Impact
- Incorrect metamodel typing will cause Capella model validation errors
- Traceability from SA → LA → PA will be broken or misleading since LA functions should be realizations of SA SystemFunctions, not siblings of the same type
- Any tool or report that queries function type will return incorrect results
- Functional chains built on these functions inherit the incorrect typing

### Root cause hypothesis
capellambse does not infer the correct function subtype from the parent container context. When extending a `SystemFunction` with `functions:`, it defaults to creating `LogicalFunction` objects rather than `SystemFunction` objects. An explicit type discriminator in the patch YAML may be required.

### Potential patch YAML fix to investigate
```yaml
- parent: !uuid <root-system-function-uuid>
  extend:
    functions:
      - name: "My Function"
        _type: SystemFunction
```
Or alternatively via the capellambse class name:
```yaml
      - _capella_type: ctx:SystemFunction
        name: "My Function"
```
Neither syntax has been confirmed to work — requires investigation by the capella-fabric MCP developer.

### Required remediation in current model
All 17 functions in the Road Grader Front Axle Assembly SA layer need to be retyped from `LogicalFunction` to `SystemFunction`. Options:
1. Delete and recreate all 17 functions correctly in Capella manually
2. Edit the `.capella` XML directly — find all `LogicalFunction` elements under the SA `SystemFunctions` package and change their xsi:type from `la:LogicalFunction` to `ctx:SystemFunction`
3. Wait for a capella-fabric patch fix that enables correct typing, then repatch

### Recommendation
Engineer to decide on remediation approach. Option 2 (XML edit) is fastest if the engineer is comfortable with XML. Option 1 (manual recreation in Capella) is safest. Option 3 defers the fix but leaves the model in an invalid state in the interim.

Until resolved, Knowledge Partner should NOT create SA functions via `extend: functions:` patch — this will continue to produce incorrectly typed objects.

---

## 2026-06-11T15:32:33Z — milestone

## ISSUE-009 RESOLVED — SystemFunction type now created correctly via patch

**Resolution date:** 2026-06-11
**Fixed by:** Claude Code ("the cousin") — Option 3 fix to capella-fabric MCP patch handler

### Verification test
Created a test function via `extend: functions:` under Root System Function (uuid: 733022d8). Result:

```
name: Test System Function
type: SystemFunction   ← CORRECT
layer: SA              ← CORRECT
parent: Root System Function
```

Previous behaviour produced `type: LogicalFunction, layer: LA`. Fix confirmed working.

### Related fixes also confirmed resolved
- ISSUE-008 (allocation failure) was a downstream symptom of ISSUE-009. With correct SystemFunction typing, `allocated_functions` patches should now also work correctly. To be confirmed on next actor allocation attempt.

### Residual action
Test function `DELETE ME — ISSUE-009 test function` (uuid: 0531c0af) left in model — engineer to delete manually in Capella. Note: `delete:` patch syntax not yet supported by capella-fabric (logged as part of ISSUE-009 fix scope).

### Outstanding work unblocked by this fix
- Rewire [SAB] CAP-01 functional exchanges and functional chain to new SystemFunction UUIDs
- Actor function allocations can now be patched directly (no manual step required)
- Remaining 5 capability SABs (CAP-02 through CAP-06) can be built with confidence

---

## 2026-06-11T18:16:45Z — observation

## ISSUE-004 recurrence — Agent artifact push caused non-fast-forward for engineer

**Date:** 2026-06-11, [LAB] Structure camber design decision session
**Related issue:** ISSUE-004

### What happened
Engineer had uncommitted Capella model changes in their local working copy. Knowledge Partner pushed an artifact log entry (camber design decision, commit d0ba44ea) to master. Engineer then attempted to push their Capella changes and received a non-fast-forward rejection because remote had advanced.

### Root cause
Same as ISSUE-004 — shared master branch used for both model files and artifact logs means any push from the agent can block the engineer's pending push. The agent pushed the artifact log immediately after receiving engineer confirmation of the design decision without first confirming the engineer had already pushed their model changes.

### Recovery
Engineer runs `git pull --rebase origin master` to replay local commits on top of agent push, then `git push origin master`.

### Workflow improvement identified
Agent should always ask "have you pushed your Capella changes yet?" before pushing any artifact log entry to master during an active modeling session. This is a behavioral guideline gap — the system prompt covers model-patch-before-log-push ordering but not the engineer local changes scenario.

### Recommended system prompt addition
Add to behavioral guidelines: "Before pushing any artifact log entry, confirm the engineer has no pending unpushed Capella model changes. If unsure, ask explicitly before calling push_artifacts."

---

## 2026-06-11T18:35:38Z — issue

## ISSUE-010 · FunctionalChain involvement cannot be patched — no model-coupled attribute found

**Tool:** capella-fabric (`apply_model_patch`)
**Status:** Open — requires investigation by cousin (Claude Code)
**First observed:** 2026-06-11, Road Grader LA Steering Control functional chain session
**Blocking:** Partial — functional exchanges can be created, but chain involvement must be done manually in Capella

### Description
Attempting to add functions and exchanges to a `FunctionalChain` via `apply_model_patch` using `extend:` fails regardless of which attribute name is used. All known attribute variants return errors indicating the attribute is either not found or not model-coupled.

### Errors encountered
```
Cannot create object: FunctionalChain.involved_links is not model-coupled
'FunctionalChain' object has no attribute 'involved_elements'
Cannot create object: FunctionalChain.involved is not model-coupled
Cannot create object: FunctionalChain.involved_functions is not model-coupled
Cannot create object: FunctionalChain has no attribute 'involved_exchanges'
```

### Context
The existing LA `Steering Control` functional chain (uuid: a0be678c) was created by the SA→LA transition and already has involvement set for 6 functions and 5 exchanges. The goal was to extend it with 3 new functions and 4 new functional exchanges created for the LH/RH cylinder decomposition.

### What worked
Creating functional exchanges via `extend: exchanges:` on the `Root Logical Function` parent worked correctly (commit d7d48a75). Four new exchanges created: Hydraulic to Cylinder LH/RH, Cylinder Displacement LH/RH.

### What failed
All attempts to add these new exchanges and the new functions (Route hydraulic pressure to cylinder, Actuate steering cylinder LH, Actuate steering cylinder RH) to the FunctionalChain involve list via patch.

### Workaround
Add functions and exchanges to the functional chain manually in Capella via the chain editor — drag functions and exchanges onto the chain, or use the involvement dialog. Commit and push after manual step.

### For cousin investigation
Need to identify the correct capellambse attribute name for FunctionalChain involvement. The fabric YAML shows `involve:` as a display label with both `LogicalFunction` and `FunctionalExchange` objects listed. The underlying capellambse attribute may be `involved_function_ports`, `involvement_links`, or accessed via `FunctionalChainInvolvement` objects. Check capellambse source for `FunctionalChain` class definition.

---

## 2026-06-12T02:26:39Z — observation

## OBS-003 · Artifact repo and Capella model repo should be separate repositories

**Source:** Road Grader Front Axle Assembly modeling sessions, 2026-06-10 through 2026-06-11
**Category:** Workflow architecture recommendation

### Observation
Throughout the Road Grader sessions the Knowledge Partner artifact log and the Capella model files share the same GitHub repository (tkSDISW/Road_Grader_Front_Axel_Assembly). This arrangement has been a persistent source of friction and has directly caused multiple session disruptions.

### Problems observed from co-locating artifacts and model in one repo

**1. Non-fast-forward conflicts (ISSUE-004, recurring)**
The agent pushes artifact log entries to master. The engineer pushes Capella model changes to master. Because both are writing to the same branch independently, non-fast-forward rejections occur regularly — requiring git pull --rebase recovery cycles. This was observed four times across the Road Grader sessions alone.

**2. Push timing discipline required**
The engineer must ensure all Capella changes are pushed before the agent logs anything, and the agent must confirm the engineer has pushed before writing to the log. This is a cognitive overhead that interrupts modeling flow and has been violated multiple times even with awareness of the issue.

**3. Mixed commit history**
The git log for the model repo contains a mixture of Capella model commits and artifact log commits. This pollutes the model change history, making it harder to trace model evolution independently of knowledge management activity.

**4. Artifact repo session lag**
When the agent's artifact session is cloned from the same repo as the model, any model patch push advances HEAD and immediately invalidates the artifact session, requiring a re-clone before the next artifact write.

**5. Binary/text conflict risk**
Capella model files (.capella, .aird, .melodymodeller) are binary XML. Artifact log files are plain text. Storing both in the same repo increases the risk of merge conflicts that are difficult or impossible to resolve automatically.

### Recommended architecture
Separate the two concerns into two dedicated repositories:

| Repo | Contents | Writers |
|---|---|---|
| `<project>_model` | Capella model files (.capella, .aird) | Engineer only |
| `<project>_knowledge` | Artifact logs, reference docs, requirements | Knowledge Partner agent |

The capella-fabric MCP clones the model repo. The artifact-repo MCP clones the knowledge repo. Neither agent ever writes to the other's repo. Push conflicts become structurally impossible.

### Additional benefit
A dedicated knowledge repo can be branched and tagged independently of the model, enabling knowledge artifacts to have their own versioning cadence (e.g. a requirements baseline that references a specific model commit SHA without being entangled in the model branch history).

### Effort to adopt
Low for new projects — simply create two repos from the start. For existing projects like Road Grader, the artifact package can be migrated to a new dedicated repo in one push with history preserved.

---

## 2026-06-12T02:29:39Z — note

## NOTE: Consider alternative naming conventions for Knowledge Partner repositories

**Related to:** OBS-003 — separate artifact and model repos
**Category:** Workflow architecture / naming convention

### Context
The current repo name `knowledge_partner` is functional but generic. As the KP workflow matures and potentially open-sources, repository naming should communicate purpose clearly to new users and distinguish the two repo roles (model vs. knowledge) at a glance.

### Naming dimensions to consider
A good repo name pair should convey:
- The project or system being modeled
- Which role the repo plays (model files vs. knowledge/artifacts)
- Optionally, the toolchain or methodology (Capella, MBSE)

---

### Example naming patterns

**Pattern 1 — Suffix approach (simplest)**
```
Road_Grader_Front_Axle_Assembly          ← Capella model files
Road_Grader_Front_Axle_Assembly_kp       ← Knowledge Partner artifacts
```

**Pattern 2 — Explicit role suffix**
```
Road_Grader_Front_Axle_model             ← Capella model files
Road_Grader_Front_Axle_knowledge         ← Knowledge Partner artifacts
```

**Pattern 3 — MBSE convention inspired by Cameo/MagicDraw team norms**
```
Road_Grader_Front_Axle_mbse              ← Capella model files
Road_Grader_Front_Axle_mbse_log          ← Knowledge Partner artifacts
```

**Pattern 4 — SE discipline naming**
```
Road_Grader_Front_Axle_capella           ← Capella model files
Road_Grader_Front_Axle_se_artifacts      ← Knowledge Partner artifacts
```

**Pattern 5 — Short and pragmatic**
```
rg_axle_model                            ← Capella model files
rg_axle_kp                               ← Knowledge Partner artifacts
```

**Pattern 6 — Hierarchical org structure (for multi-project orgs)**
```
<org>/systems/<project>_model            ← Capella model files
<org>/knowledge/<project>_artifacts      ← Knowledge Partner artifacts
```

---

### Recommendation
Pattern 2 (`_model` / `_knowledge`) is the clearest for open-source documentation and onboarding — the role of each repo is unambiguous without knowing the toolchain. Pattern 1 (`_kp` suffix) is the lightest touch for existing projects that want to add a knowledge repo alongside an existing model repo.

For the current `knowledge_partner` global issues repo, consider renaming to `se_kp_tooling` or `capella_kp_issues` to signal its scope more clearly to external contributors.

### Action
No immediate change required — record for consideration when formalizing the open-source workflow documentation or onboarding new projects.

---

## 2026-06-12T14:47:47Z — issue

## ISSUE-007 RECURRENCE · Duplicate UUID c1d22496 reappeared in model fragment

**Date:** 2026-06-12
**Related:** ISSUE-007 (first occurrence 2026-06-11)
**Status:** Open — engineer action required again
**Blocking:** Yes — all capella-fabric operations blocked

### Description
The duplicate UUID c1d22496-a4f3-4fa9-888c-1cbee21d4adb has reappeared in Road_Grader_Front_Axel_Assembly.capella, blocking all model queries. This is the second occurrence of the exact same UUID being duplicated.

### Significance of recurrence
The fact that the same UUID is duplicated a second time is a strong signal that there is a specific repeatable trigger in Capella. This is not random corruption — something about the workflow reproducibly causes this particular element to be duplicated.

### Likely trigger pattern
The first occurrence happened during creation of the [SAB] Road Grader Context View diagram. The second occurrence appears to have happened during LA modeling work (functional chain creation or diagram work in the LA layer). The common thread is likely a copy/paste or diagram element duplication operation involving the element with this UUID.

### Candidate element
UUID c1d22496 was first identified as belonging to an element in the SA layer (possibly an actor or component that was also present in the LA transition). The LA transition itself may have produced a reference to this UUID, and subsequent diagram operations may be duplicating it. Worth identifying definitively which model element owns this UUID — it is likely an actor (Hydraulic System, Grader Super Structure, or similar) that appears in both SA and LA contexts.

### Recovery steps (same as ISSUE-007)
1. Open model in Capella
2. Right-click model root → Validate — identifies the duplicate element
3. Delete the duplicate (keep the original)
4. Save, commit, push to master
5. Notify Knowledge Partner to re-clone

### Recommended additional step this time
After recovery, identify which element owns UUID c1d22496 and document it here. Also note what operation was being performed in Capella immediately before the duplicate appeared — this will help isolate the trigger for a permanent fix.

---

## 2026-06-12T15:21:12Z — note

## ISSUE-007 UPDATE · Duplicate UUID root cause — Library project type likely contributor

**Date:** 2026-06-12
**Status:** Partially resolved — individual occurrences cleared manually; root cause identified but not fully eliminated

### Recovery method confirmed
Engineer was able to clear the duplicate by deleting the stub root Library element directly in Capella (without requiring a full model revert as in the first occurrence). Confirmed the stub at line 1798 is the correct element to delete — it contains only ModelInformation and projectApproach key-value, while the real model content is in the first Library element at line 20.

### Root cause hypothesis — Library project type
The Road Grader model is a **Capella Library project** rather than a standard Capella project. This is a significant finding. In Capella, Library projects have different serialization behavior — they use `org.polarsys.capella.core.data.capellamodeller:Library` as the root XMI element rather than `org.polarsys.capella.core.data.capellamodeller:Project`. Certain Capella operations that initialize or re-register a project (such as the SA→LA architecture transition wizard, library reference resolution, or team-for-Capella synchronization) may re-write or append the Library root element rather than updating the existing one, producing a duplicate root with the same UUID.

### Why the same UUID appears twice
Capella generates UUIDs deterministically for certain structural elements (root library, model information) based on project identity. When an operation re-initializes the Library root, it reuses the same UUID rather than generating a new one, producing a true duplicate rather than a collision between two independently generated IDs.

### Operations that may trigger the duplicate
- SA→LA or LA→PA architecture transition wizard
- Adding or re-registering a library reference
- Model repair or migration operations
- Possibly: opening the model in a different Capella version or with a different set of plugins

### Recommended precaution
Before running any architecture transition, library registration, or model repair operation in Capella, commit the current clean model state to git. This ensures a known-good rollback point is always available within a few minutes of work.

### Longer term
If OBEO tighter integration is adopted (per OBS-001), this issue may be mitigated by server-side model management that controls serialization. Worth flagging to the OBEO team as a known behavior with Library projects under git version control.

### XML signature of the bad element (for future reference)
When the duplicate appears, it is always the LAST Library element in the file, just before `</xmi:XMI>`. It contains only:
```xml
<org.polarsys.capella.core.data.capellamodeller:Library id="c1d22496-..."
    name="Road_Grader_Front_Axel_Assembly">
  <ownedExtensions xsi:type="libraries:ModelInformation" id="..."/>
  <keyValuePairs xsi:type="...KeyValue" key="projectApproach" value="SingletonComponents"/>
</org.polarsys.capella.core.data.capellamodeller:Library>
```
Safe to delete. The real model content is in the first Library element.

---

## 2026-06-13T13:56:28Z — decision

## DECISION: Curated Knowledge as the Central Goal of the SE Knowledge Partner

**Date:** 2026-06-12
**Author:** Engineer / Knowledge Partner session
**Scope:** Research paper framing and demonstration strategy

### Decision
The paper and demonstration examples will be framed around **curated knowledge as the primary goal** of working with a system model through an AI Knowledge Partner. The central argument is that a system model, in its raw form, is data — not knowledge. The Knowledge Partner's role is to extract, interpret, organize, and persist engineering insight from that data into a form that can be reasoned over, referenced, and reused across the engineering lifecycle.

### Rationale
Throughout the Road Grader Front Axle Assembly sessions this principle emerged clearly from practice. The model contained components, functions, exchanges, and chains — but the engineering knowledge lived in the interpretive layer: why the camber actuator connects only to the RH knuckle, what the tie rod synchronization tolerance means for vehicle controllability, why the Library project type causes duplicate UUID artifacts, how frequent commits enable rollback from model corruption. None of that was in the model. It had to be extracted, reasoned over, and captured deliberately.

The KP workflow makes this extraction systematic rather than incidental.

### What curated knowledge means in this context
Raw model content (UUIDs, component names, exchange lists) becomes curated knowledge when it has been:

1. **Extracted** — pulled from the model via fabric generation and interpreted through an SE lens rather than as raw XML
2. **Contextualized** — connected to engineering intent, design decisions, physical evidence (CAD), and operational context
3. **Validated** — reviewed against the engineer's domain knowledge and corrected where the model diverges from intent
4. **Enriched** — augmented with descriptions, rationale, traceability, and testable values that the model schema alone cannot carry
5. **Persisted** — written back to a structured artifact repository where it can be queried, versioned, and reasoned over in future sessions

### Evidence from Road Grader sessions
The sessions produced the following curated knowledge artifacts that did not exist in the raw model:

- Six SA capabilities with descriptions, actor involvements, and engineering rationale
- Actor descriptions explaining the role of each external system in the assembly context
- Functional exchange names that encode the engineering meaning of each data flow
- A design decision on camber architecture (single actuator, asymmetric linkage, two-way valve) grounded in CAD evidence
- 19 system requirements with testable acceptance criteria traceable to functional exchanges
- Workflow observations and issues that capture institutional knowledge about the toolchain
- A CAD reference artifact that connects physical evidence to model abstractions

None of these existed in the Capella model files. They were produced through the extraction-interpretation-curation cycle.

### Implications for the paper
The paper should argue that:
- MBSE tools produce structured data, not knowledge — the gap between the two is where engineering value is lost
- AI agents can close this gap by acting as a persistent, interactive curation layer between the model and the engineer
- The KP workflow demonstrates this concretely: every session produces not just model changes but a growing body of interpreted, persisted, queryable knowledge
- Frequent model commits combined with a dedicated knowledge repository create a dual audit trail — one of model state, one of engineering understanding — that together constitute a living systems engineering record

### Demonstration strategy
Use the Road Grader Front Axle Assembly as the running example. Show the progression:
- Raw model (skeleton state, session 1) → structured capabilities → functions and exchanges → requirements → LA decomposition → curated knowledge artifacts
- At each step, contrast what was in the model with what the KP extracted and curated
- Emphasize that the knowledge repo is queryable and reasoned over — not just a log, but a foundation for future engineering decisions

---

## 2026-06-13T16:29:51Z — decision

## DECISION: Functional Chain as Foundation for FMEA and P-Diagram

**Date:** 2026-06-13
**Scope:** Paper demonstration strategy — downstream knowledge products

### Decision
The Steering Control and Camber Control functional chains will serve as the foundation for two downstream knowledge products to be developed in a future session:

1. **FMEA (Failure Mode and Effects Analysis)** — seeded directly from the functional exchange structure of both chains
2. **P-Diagram (Parameter Diagram)** — derived from the chain's signal factors, ideal response, control factors, and noise factors

Both will be demonstrated as outputs of the KP curated knowledge workflow, reinforcing the central paper thesis that a single curated artifact (the functional chain) is a reusable engineering foundation for multiple downstream products.

### Why functional chains are ideal FMEA inputs
Each functional exchange in the chain defines a potential failure point. The functions on either side define local effect (what the receiving function loses) and end effect (what the chain's terminal output loses). The propagation path — the hardest part of FMEA to construct manually — already exists in the chain structure. No re-entry required.

### Steering Control chain — preview failure propagation paths
| Exchange | Failure Mode | End Effect |
|---|---|---|
| Hydraulic Pressure Supply | Loss of pressure | Loss of steering |
| Valve Open Signal | Valve fails closed | No cylinder actuation |
| Actuator Force LH/RH | Cylinder rod seizes | Steering lock |
| Tie Rod Sync Force LH/RH | Tie rod fracture | Wheel angle divergence — instability |
| Constrained Steering Angle | Stop fails to engage | Steering over-travel |
| Camber Transfer Force | Camber Assembly fracture | Asymmetric camber — handling degradation |

### P-Diagram structure
- Signal factors: Steering command, hydraulic pressure input
- Ideal response: Wheel angle output, synchronization accuracy, force output (SC-014 through SC-016)
- Control factors: Valve setting, stop angle, cylinder bore
- Noise factors: Temperature (SC-017), wear (SC-018), terrain loads, pressure variation, seal degradation (SC-019)
- Error states: Loss of steering, sync deviation, creep, leakage

### Multiplier effect — key paper argument
One curated functional chain seeds:
- FMEA failure propagation paths
- P-diagram parameter structure
- Requirements verification matrix (via SC-001 through SC-019)
- Test case hierarchy
- Functional allocation traceability to physical components

This is the multiplier effect of knowledge curation — build once with the KP, reuse across the engineering lifecycle without redundant re-entry.

### Next session action
Engineer to provide latest model state (both Steering Control and Camber Control chains finalized). Knowledge Partner to re-clone and generate FMEA draft artifact seeded from both chains as a structured table artifact in the Road Grader knowledge package.

### Status
Deferred — pending engineer push of latest model updates.

---

## 2026-06-13T17:31:16Z — issue

## ISSUE-011 · Engineer name not captured in commits or artifacts — identity traceability gap

**Tool:** capella-fabric (`apply_model_patch`, `push_model_changes`), artifact_repo (`write_artifact`, `add_log_entry`)
**Status:** Open — investigation required
**Related:** ISSUE-002 (author identity on commits)
**First observed:** Throughout Road Grader sessions 2026-06-10 through 2026-06-13

### Description
All model patches and artifact log entries are committed under the Knowledge Partner service account identity. The engineer's name does not appear in git commit author fields, artifact metadata, or log entry content unless manually embedded in commit messages (the ISSUE-002 workaround). This creates a traceability gap — it is not possible to determine from the repository alone which engineer initiated, reviewed, or approved each model change or knowledge artifact.

### Why this matters
In a multi-engineer or audited MBSE environment, knowing who made a decision or approved a model change is as important as knowing what changed. Engineering records without named authors have reduced accountability and traceability value. For the paper, demonstrating named engineer attribution would strengthen the case for KP as a production-grade SE tool rather than a prototype.

### Hypothesis — system prompt is the likely solution
The engineer name could be introduced via the system prompt in one of two ways:

**Option A — Static declaration in system prompt**
Add a field to the system prompt that declares the active engineer identity:
```
## Active Engineer
Name: [Engineer Name]
Email: [engineer@org.com]
```
The KP would then embed this identity in all commit messages, artifact author fields, and log entries automatically. Simple to implement — just a system prompt edit. Works for single-engineer sessions.

**Option B — Session initialization prompt**
At the start of each session, the engineer introduces themselves explicitly:
"I am [Name], starting a session on [project]."
The KP captures this and uses it throughout the session for attribution. More flexible for multi-engineer environments — no system prompt change required per engineer.

**Option C — capella-fabric author_name parameter (when implemented)**
ISSUE-002 notes that an `author_name` parameter is planned for `apply_model_patch`. Once available, the system prompt identity would be passed directly as the git committer, giving true git author attribution rather than just commit message embedding.

### Recommended immediate action
Add Option A to the system prompt as an interim solution — it requires no tooling changes and would immediately improve attribution in commit messages and artifact metadata. The PAT placeholder pattern already in the system prompt (`{{ghp_...}}`) establishes a precedent for this kind of identity field.

### Suggested system prompt addition
```
## Active Engineer
Name: {{ENGINEER_NAME}}
Email: {{ENGINEER_EMAIL}}
```
KP behavioral guideline: embed `[ENGINEER_NAME]` in all commit messages and as the `author` field in all artifact writes and log entries.

### Longer term
Combine with Option C (capella-fabric author_name parameter) once implemented to achieve true git committer identity rather than message-embedded attribution.

---

## 2026-06-15T17:13:48Z — issue

## ISSUE-012 · PA NODE component creation via patch produces Part objects — corrupts model file

**Tool:** capella-fabric (`apply_model_patch`)
**Status:** Open — requires cousin investigation
**First observed:** 2026-06-15, Road Grader PA layer — NODE component creation session
**Severity:** High — model file fails to load in Capella after patch applied
**Engineer action:** Rolled back to last known good commit

### Description
Attempting to create Physical Architecture NODE components via `apply_model_patch` using `extend: owned_components:` with `nature: NODE` results in `Part` objects being created in the model rather than true `PhysicalComponent` elements typed as NODE. The resulting `.capella` file fails to load in Capella.

### Symptom
After patch commit `785f91f0`, the model would not open in Capella. Part objects were visible in the model tree instead of the expected NODE-typed PhysicalComponent elements.

### Reproduction
```yaml
- parent: !uuid <physical-system-uuid>
  extend:
    owned_components:
      - name: "Steering Cylinder LH Node"
        nature: NODE
```
Results in: Part objects in model, file load failure.

### What worked for attribute discovery
- `owned_components` was identified as the correct extend attribute (committed successfully, no error returned)
- `nature: NODE` was accepted without error
- `deployment_links` was identified as correct for deploying behavior to nodes
- `!promise` / `promise_id:` worked for forward references
- However: despite no patch errors, the resulting model elements are malformed

### Root cause hypothesis
capellambse's `owned_components` attribute on `PhysicalComponent` may be creating `Part` ownership objects rather than child `PhysicalComponent` elements. In Capella's metamodel, `PhysicalComponent` ownership is represented differently from `LogicalComponent` — the PA layer uses a `Part`/`Component` split that capellambse may not be handling correctly when `nature: NODE` is set.

In capellambse, the correct way to create a NODE PhysicalComponent may require:
- An explicit `_type: PhysicalComponent` with `nature: NODE` on the owned element
- Or a different container attribute such as `sub_components` or `owned_physical_components`
- Or the NODE nature may need to be set via a separate `set:` operation after creation

### For cousin investigation
1. Check capellambse source for `PhysicalComponent` — what attribute creates child `PhysicalComponent` elements vs `Part` objects?
2. Verify `nature` is a valid settable attribute on `PhysicalComponent` and maps to the correct Capella `kind` enum value (`NODE` vs `BEHAVIOR` vs `UNSET`)
3. Test minimal patch: create one NODE component, inspect the resulting XML to confirm `xsi:type` and `kind` attributes are correctly set
4. Check whether `deployment_links` creates the correct `ComponentDeploymentLink` element or a different deployment artifact

### Workaround
NODE components must be created manually in Capella until this is resolved. The patch handler correctly discovers existing NODE components (fabric shows them as `PhysicalComponent Node`) but cannot create new ones reliably via patch.

### Engineer action taken
Rolled model back to the commit before `785f91f0` (port name patch `e46a6247` was the last clean state).

---

## 2026-06-15T22:38:24Z — observation

## OBS-004 · Curated knowledge as foundation for prompt-driven automatic architecture review boards

**Source:** Road Grader PA property value session, 2026-06-15
**Category:** Future capability — high value application of KP knowledge base

### Observation
The curated knowledge accumulated in the Knowledge Partner repository — capabilities, functions, exchanges, requirements, property values, design decisions, and observations — is a natural foundation for **prompt-driven automatic architecture review**. Rather than waiting for scheduled human review boards, the KP could instantiate virtual review board participants as prompts, each with a defined role and perspective, and run them against the model knowledge base automatically.

### Concept
A system prompt would define a review board with distinct engineering roles, each instantiated as a separate prompt perspective. Examples:

| Role | Focus | Prompt framing |
|---|---|---|
| Systems Architect | Completeness and traceability across OA/SA/LA/PA layers | "Review the model for missing allocations, untraced functions, and layer coverage gaps" |
| Safety Engineer | Failure modes and hazard coverage | "Identify functions with no redundancy, single points of failure, and unmitigated hazards" |
| Requirements Engineer | Requirements coverage and testability | "Flag functions and exchanges with no traced requirement, and requirements with no acceptance criteria" |
| Mechanical Engineer | Physical realizability and property value completeness | "Identify PA components missing mass, material, or dimensional property values" |
| Integration Engineer | Interface completeness and exchange naming | "Find unnamed exchanges, ports without allocations, and components with no component exchanges" |
| Configuration Manager | Model integrity and change traceability | "Identify uncommitted work log items, open issues, and decisions without model impact recorded" |

### Why this works with the KP approach
The curated knowledge base makes this possible. Raw model XML is not reviewable by a prompt — it's data. But the fabric, enriched with descriptions, named exchanges, property values, design decisions, and work log entries, IS reviewable. The KP has already demonstrated this — every fabric review session in the Road Grader work was effectively a single-role automated review. A multi-role review board is the natural generalization.

### Implementation approach
Each review board role would be a `prompt_def` artifact in the knowledge repo, rendered via `render_prompt` with the current model fabric as input. Results would be written as `issue` or `observation` log entries automatically. The engineer could then triage and act on the findings.

### Value for the paper
This extends the curated knowledge thesis significantly:

> *Curated knowledge doesn't just enable human reasoning — it enables automated reasoning. A KP knowledge base that is rich enough for a human engineer to reason over is also rich enough for a prompt-driven review board to reason over. The same investment in curation yields both human insight and automated quality assurance.*

### Immediate and automatic issues
A lightweight version of this already exists implicitly in the KP workflow — every fabric review session produces issues automatically (typos, unnamed exchanges, missing functions, wrong types). Formalizing this as a scheduled automatic review on every model push would catch issues without requiring an engineer to ask.

### Priority
High — this is a compelling demonstration of the multiplier effect of curated knowledge and a strong addition to the paper's argument. Consider implementing a prototype review board for the Road Grader demo using the Steering Control and Camber Control chains as the review scope.

---

## 2026-06-15T22:42:37Z — observation

## OBS-005 · Improved modeling velocity exposed bookkeeping as a bottleneck — led organically to KP logging

**Source:** Road Grader modeling sessions, 2026-06-10 through 2026-06-15
**Category:** Workflow evolution — key insight for paper

### Observation
The Knowledge Partner significantly improved modeling velocity — capabilities, functions, exchanges, descriptions, and property values could be patched into the model faster than an engineer working alone in Capella. However, this speed increase exposed a new bottleneck: **bookkeeping**.

When modeling moves faster, the gap between what has been done and what has been recorded grows quickly. Without documentation keeping pace, the session leaves behind a model that has changed but no human-readable record of why, what decisions were made, what issues were encountered, or what remains open.

### How KP logging emerged
KP logging was not designed upfront as a feature — it emerged organically as the natural response to this bottleneck. Once modeling velocity increased, the engineer and KP began capturing:

- Work log milestones after each significant modeling step
- Design decisions at the point they were made (camber architecture, Ackermann geometry, cylinder redundancy)
- Issues as they were discovered (duplicate UUID, wrong function type, unnamed exchanges)
- Observations about workflow patterns as they emerged (commit discipline, repo separation, review board concept)

The logging happened in the same session as the modeling work, using the same KP that was doing the patching. No context switch required — the KP already had full awareness of what had just been done.

### The key insight
> *AI assistance doesn't just accelerate the work — it accelerates the work faster than human bookkeeping can keep up. The KP logging capability exists precisely because the KP itself created the need for it.*

This is a self-reinforcing loop:
- KP increases modeling velocity
- Increased velocity exposes bookkeeping as a bottleneck
- KP logging closes the bookkeeping gap
- Closed bookkeeping gap enables the next session to start with full context
- Full context enables the KP to be even more effective in the next session

### Implications for the paper
This observation reframes KP logging not as an optional add-on but as a **necessary complement to AI-assisted modeling**. Without it, the productivity gains from faster modeling are partially offset by the cost of reconstructing context at the start of each session. With it, the context is always current and the KP can operate at full effectiveness from the first message of each session.

This also explains why the knowledge repo and the model repo should be separate (OBS-003) — the logging cadence and the modeling cadence are different, and mixing them creates the non-fast-forward conflicts observed throughout the Road Grader sessions.

### Supporting evidence from Road Grader sessions
- 12 work log milestones captured across 5 days of modeling
- 12 tooling issues logged with reproduction steps, workarounds, and suggested fixes
- 5 design decisions recorded at the moment of decision with full engineering rationale
- 4 workflow observations documented as they emerged
- All of this was captured without a separate documentation session — it happened in-line with the modeling work

---

## 2026-06-15T22:45:00Z — observation

## OBS-006 · Engineer-KP collaborative modeling naturally extends to multi-role architecture review

**Source:** Road Grader modeling sessions, 2026-06-15
**Category:** Workflow evolution — narrative arc for paper
**Related:** OBS-004 (prompt-driven review boards), OBS-005 (logging as bottleneck response)

### Observation
The Road Grader sessions revealed a natural progression in how the engineer and KP work together. This progression is not accidental — each stage emerges from the limitations and opportunities exposed by the previous one.

### The progression

**Stage 1 — KP as modeling assistant**
The engineer directs, the KP executes. The KP patches components, names exchanges, fixes typos, and generates fabric reviews. The engineer provides domain knowledge and approves changes. Velocity increases significantly over solo modeling.

**Stage 2 — KP as bookkeeper**
Increased velocity exposes the bookkeeping bottleneck (OBS-005). The KP begins logging milestones, decisions, issues, and observations inline with modeling work. The knowledge base grows as a byproduct of the modeling sessions rather than as a separate documentation effort.

**Stage 3 — KP as reviewer**
The accumulated knowledge base is now rich enough to reason over. The same KP that built the model can review it — but now wearing a different hat. In the Road Grader sessions this happened naturally: every fabric pull was implicitly a review session that found issues, gaps, and inconsistencies the engineer hadn't noticed. The KP was simultaneously builder and reviewer.

**Stage 4 — Multi-role review board (emerging)**
The natural extension of Stage 3 is for both the engineer and the KP to deliberately put on different hats for a more thorough review. The engineer brings domain expertise as a Safety Engineer or Integration Engineer. The KP instantiates as a Requirements Engineer or Configuration Manager. Together they cover perspectives that neither would cover alone in a single modeling session.

This is not a new idea in systems engineering — formal design reviews have always used multiple roles for this reason. What is new is that:
- The KP can instantiate any role on demand without scheduling a meeting
- The knowledge base makes the review grounded in actual model content rather than slides
- The review findings are written directly back to the knowledge base as issues and observations
- The cycle from finding to fix is measured in minutes rather than weeks

### Why this progression is inevitable
Each stage creates the conditions for the next:
- Faster modeling (Stage 1) → needs better bookkeeping (Stage 2)
- Better bookkeeping (Stage 2) → enables grounded review (Stage 3)
- Grounded review (Stage 3) → reveals value of multiple perspectives (Stage 4)

The engineer and KP don't choose to move through these stages — the workflow pulls them forward naturally as each limitation becomes apparent.

### Implication for the paper
This progression is the central narrative arc of the paper. The Road Grader sessions are the evidence. The argument is:

> *The collaborative relationship between engineer and AI in MBSE is not static. It evolves through stages — from assistant to bookkeeper to reviewer to multi-role review board — driven by the increasing richness of the curated knowledge base. Each stage is a natural response to the opportunities and limitations exposed by the previous one. The endpoint is not a tool that helps an engineer model faster — it is a collaborative intelligence that helps a team think more thoroughly.*

### For the demo
Show the progression explicitly:
1. Start with the skeleton model (Stage 1 entry point)
2. Show the knowledge artifacts produced alongside the model (Stage 2)
3. Run a fabric review live, finding and fixing issues (Stage 3)
4. Instantiate a two-role review — engineer as Safety Engineer, KP as Requirements Engineer — against the Steering Control chain (Stage 4)

---

## 2026-06-15T22:53:34Z — observation

## OBS-007 · A minimal set of three service primitives is sufficient to extract model content for AI reasoning

**Source:** Road Grader modeling sessions, 2026-06-10 through 2026-06-15
**Category:** Architecture insight — tooling minimalism
**Related:** OBS-006 (progression of engineer-KP collaboration)

### Observation
Throughout the Road Grader sessions, all model content extraction for reasoning was accomplished using just three service primitives:

1. **Search** — `search_model_objects` and `browse_model` — locate objects by name, type, and phase
2. **List** — `list_object_types`, `browse_knowledge_repo`, `list_artifact_packages` — enumerate what exists in the model or knowledge base
3. **Semantic fabric** — `generate_fabric` scoped to a diagram, functional chain, or resolved object — produce a rich, structured, human-readable representation of model content that an AI can reason over

That is the complete read stack. Every fabric review, every exchange scan, every component analysis, every traceability check in the Road Grader sessions was performed using some combination of these three primitives.

### Why this is architecturally significant
The Capella metamodel is extremely complex — hundreds of object types, thousands of possible relationships, deeply nested XML structures that are not human-readable in raw form. Traditional MBSE tool integrations require extensive API surface area to navigate this complexity.

The KP approach sidesteps this by using fabric generation as a **semantic compression layer**. Rather than exposing the full metamodel API, the fabric tool:
- Resolves references and follows relationships automatically
- Presents content in a structured YAML-like format that an LLM can parse naturally
- Scopes output to a diagram or chain, keeping the context window manageable
- Preserves engineering meaning (names, descriptions, allocations, exchanges) while discarding raw XML noise

The result is that a surprisingly small API surface area — search, list, fabric — is sufficient for an AI to reason over a professional-grade MBSE model.

### Implications for open-sourcing and adoption
A minimal API surface has major adoption advantages:
- **Low implementation cost** — three primitives are far easier to implement for a new MBSE tool than a full API
- **Portable pattern** — the same search/list/fabric pattern could work for MagicDraw, Rhapsody, Arcadia, or any model-based tool that can produce structured output
- **LLM-friendly** — fabric output is designed to be read by an LLM, not parsed by code — this is a fundamentally different design philosophy from traditional MBSE APIs
- **Extensible** — write primitives (patch, push, verify) were added later without changing the read architecture

### The write stack is equally minimal
On the write side, `apply_model_patch` with YAML conventions covers the vast majority of model modifications. The patch handler abstracts the metamodel complexity in the same way that fabric abstracts read complexity. Two stacks, three primitives each, covering the full read-write lifecycle of an AI-assisted MBSE session.

### For the paper
> *The KP tooling demonstrates that AI-assisted MBSE does not require full API coverage of the modeling tool's metamodel. A minimal set of three read primitives — search, list, and semantic fabric — is sufficient to extract model content in a form that an LLM can reason over. The fabric generation step is the key architectural innovation: it acts as a semantic compression layer that translates complex metamodel structures into LLM-readable representations without losing engineering meaning.*

This is a counter-intuitive but important finding. The temptation in MBSE tool integration is to expose more API surface. The KP experience suggests the opposite — the right approach is to compress the model into a semantically rich but structurally simple representation, and let the LLM do the reasoning from there.

---

## 2026-06-15T23:06:04Z — observation

## OBS-008 · Original intent superseded — artifacts and log are a richer source for replayable routines than chat logs

**Source:** Road Grader modeling sessions reflection, 2026-06-15
**Category:** Foundational insight — evolution of the KP concept
**Related:** OBS-005 (logging), OBS-006 (progression), OBS-007 (minimal primitives)

### Original intent
The Knowledge Partner was originally conceived as a tool that would capture interactive chat sessions with an engineer and transform them into replayable, executable routines — Jupyter notebooks or scripts that could automate recurring modeling tasks. The chat log was the source material; the routine was the output.

### What actually emerged
The Road Grader sessions revealed a more powerful pattern. Rather than mining raw chat logs — which are conversational, context-dependent, and full of exploratory dead-ends — the curated knowledge artifacts and work log entries are a far richer and more reliable source for routine development.

The work log milestones already describe, in structured form:
- What patches were applied and in what order
- Which UUIDs were targeted
- What the engineering intent was
- What succeeded, what failed, and what workarounds were used
- What the preconditions were (model state, prior commits)

This is precisely the information needed to construct a replayable routine — and it was captured as a byproduct of the modeling work, not as a separate documentation effort.

### Why artifacts beat chat logs as routine sources

| Dimension | Chat log | Artifact / work log |
|---|---|---|
| Signal-to-noise | Low — full of exploratory back-and-forth, corrections, retries | High — only successful outcomes recorded |
| Structure | Unstructured natural language | Structured milestone entries with UUIDs, commits, intent |
| Replayability | Hard — context-dependent, session-specific | High — patch YAML is already executable |
| Generalizability | Low — tied to specific conversation flow | Higher — milestone pattern can be abstracted |
| Failure documentation | Buried in conversation | Explicit issue entries with workarounds |

### The new routine development pattern
Instead of: `chat log → extract steps → write routine`

The emerging pattern is: `work log milestone → extract patch sequence → parameterize → routine`

A work log milestone like "Add SA system functions under Root System Function" already contains:
- The parent UUID pattern
- The extend attribute (`functions:`)
- The function names and descriptions
- The commit SHA for verification
- The known failure modes (ISSUE-009 — wrong function type, now resolved)

That is a routine in near-executable form. The KP could render it as a Jupyter notebook or Google Colab routine directly from the artifact.

### Connection to prompt_def artifacts
The `render_prompt` tool in the artifact repo already supports Jinja2 prompt templates. A `prompt_def` artifact that takes a work log milestone as input and renders it as a parameterized patch routine is a natural next implementation step — closing the loop from curated knowledge back to executable tooling.

### Implication for the paper
> *The original vision for the Knowledge Partner — capturing chat sessions and turning them into replayable routines — was correct in intent but wrong in source material. The Road Grader experience shows that curated work log artifacts are a far richer source for routine development than raw conversational transcripts. The act of curation that makes knowledge useful for human reasoning also makes it useful for routine generation. The knowledge base is not just a record of what was done — it is the seed of what can be automated.*

### Naming suggestion
The progression from interactive session → curated artifact → replayable routine could be described as the **KP knowledge flywheel**:
- Sessions produce artifacts
- Artifacts enable reasoning
- Reasoning produces better sessions
- Better sessions produce richer artifacts
- Richer artifacts enable routine generation
- Routines accelerate future sessions

Each turn of the flywheel increases the value of everything that came before it.

---

## 2026-06-15T23:19:20Z — note

## NOTE: The flywheel metaphor — mechanical analogy for KP knowledge momentum

**Source:** Engineer reflection, 2026-06-15
**Related:** OBS-008 (flywheel concept)

### The mechanical analogy
A flywheel on a John Deere tractor — or any early single-cylinder engine — stores rotational momentum from the power stroke and carries it through the compression and exhaust cycles where the engine produces no power. Without the flywheel, the engine stalls between ignition cycles. With it, the stored momentum bridges the gap and keeps the engine turning smoothly.

The analogy maps precisely onto the KP knowledge workflow:

| Flywheel | KP Knowledge Base |
|---|---|
| Stores momentum from the power stroke | Stores curated knowledge from active modeling sessions |
| Carries through the dead cycles | Bridges the gap between sessions when no engineer is present |
| Mass determines how much momentum is stored | Richness of artifacts determines how much context is preserved |
| Velocity determines how fast the next cycle starts | Depth of curation determines how quickly the next session reaches full effectiveness |
| Without it, the engine stalls | Without it, each session starts cold with no context |
| With it, each cycle builds on the last | With it, each session starts where the last one ended |

### The dead cycle problem in MBSE
Traditional MBSE sessions have significant dead cycles — time spent at the start of each session reconstructing context, re-reading previous decisions, re-examining the model to understand its current state. This is the compression stroke: necessary overhead that produces no forward progress.

The KP knowledge base is the flywheel that eliminates most of this overhead. The work log, design decisions, issue log, and artifact repo carry momentum from one session to the next. The next session starts not at zero but at the rotational speed the last session achieved.

### Why mass matters
A heavier flywheel stores more momentum. A richer knowledge base carries more context. The Road Grader sessions demonstrated this — by session 5, the KP could re-clone, read the work log, and immediately understand not just what had been built but why decisions were made, what issues were open, and what the next steps were. The accumulated mass of the knowledge base made each subsequent session faster to start and more effective in execution.

### For the paper
The flywheel metaphor is both technically precise and intuitively accessible — particularly resonant for an engineering audience. It captures the core value proposition of the KP knowledge base in a single image: stored momentum that bridges the gap between sessions and keeps the engineering process turning smoothly.

The Road Grader is itself a piece of heavy equipment — a machine where flywheels and momentum are engineering realities, not metaphors. There is a pleasing coherence in using a flywheel analogy to describe the knowledge architecture of a system model for a road grader front axle assembly.

---

## 2026-06-15T23:24:00Z — note

## NOTE: Complete engine analogy — the four elements of the KP knowledge engine

**Source:** Engineer, 2026-06-15
**Related:** OBS-008, flywheel metaphor note

### The complete analogy

The Knowledge Partner workflow maps precisely onto the four-stroke engine cycle:

| Engine element | KP equivalent | Role |
|---|---|---|
| **Patch tools** | capella-fabric apply_model_patch, artifact-repo write/push | Accelerate through the dead cycle — reduce the compression and exhaust overhead of context reconstruction and model manipulation |
| **Method** | The MBSE modeling approach — Capella layers, functional chains, capabilities, fabric extraction | Adds fuel — the structured engineering method provides the combustible material that enables reasoning to ignite |
| **Prompts** | Engineer questions, review requests, modeling directives | The ignition — the spark that initiates the reasoning cycle and converts method + knowledge into forward progress |
| **Knowledge** | Curated artifacts, work log, decisions, property values, requirements | The output power — the useful work produced by each cycle, stored in the knowledge base and carried forward by the flywheel |

### The complete engine statement
> *The patch tools accelerate the dead cycle. The method adds fuel to enabling reasoning. Prompts are the ignition. Knowledge is the output power.*

### How the cycles connect
In a single-cylinder engine, each stroke serves a purpose:
- **Intake** — method and model content drawn in (fabric generation, search, list)
- **Compression** — prompt formulated, context assembled, reasoning primed
- **Power** — KP reasons over model content, produces curated knowledge output
- **Exhaust** — patch applied, artifact written, knowledge persisted to repo

The flywheel (accumulated knowledge base) carries momentum from the power stroke of one session through the intake and compression of the next — so each session starts with more rotational energy than the last.

### Why this analogy works for the paper
It is mechanically precise, not merely poetic. Each element of the analogy maps to a specific, identifiable component of the KP architecture:
- The patch tools are measurably faster than manual Capella editing — quantifiable dead cycle reduction
- The method (Capella MBSE) is the structured framework without which the fuel has nothing to combust against
- The prompts are discrete, identifiable ignition events — every fabric review request, every naming patch request, every decision capture
- The knowledge artifacts are the measurable output — 12 milestones, 12 issues, 5 decisions, 4 observations produced from 5 days of Road Grader sessions

### For the paper title / framing
Consider: **"The Knowledge Engine: AI-Assisted MBSE as a Four-Stroke Knowledge Cycle"**

Or as a section heading: **"From Dead Cycles to Output Power — The KP Knowledge Engine"**

The Road Grader front axle assembly is not just the demonstration subject. It is the metaphor made physical — a machine whose own engineering depends on the same principles of stored momentum, ignition, and power stroke that describe the knowledge system used to model it.

---

## 2026-06-15T23:27:13Z — decision

## DECISION: Routine development as artifact synthesis — prompts, knowledge, and models as source materials

**Date:** 2026-06-15
**Related:** OBS-008 (original intent), flywheel notes, engine analogy

### Decision
The definition of a KP routine is refined. A routine is not a recording of a chat session — it is a **synthesis of three artifact types** that together encode a replayable engineering process:

1. **Prompt artifacts** — the ignition events, captured as `prompt_def` entries in the knowledge repo. Define what question to ask, what role to adopt, what scope to review. Replayable because they are parameterized templates, not one-time conversations.

2. **Knowledge artifacts** — the curated output of prior sessions, captured as milestones, decisions, issues, and observations in the work log. Define the engineering context, the known good patterns, the failure modes to avoid, and the design rationale to preserve.

3. **Model artifacts** — the Capella model itself, accessed via fabric generation scoped to a diagram, chain, or object. The current state of the model is the input to every routine execution — routines are model-aware, not model-static.

### Why this is a more powerful definition than the original
The original intent (chat log → routine) captured the sequence of interactions but not the engineering meaning behind them. A chat log knows what was typed. It does not know why.

The three-artifact definition captures the why:
- The prompt artifact encodes the engineering intent (what we were trying to accomplish)
- The knowledge artifact encodes the engineering rationale (why we made the decisions we made)
- The model artifact encodes the current engineering state (what the model looks like now)

A routine built from these three sources can be replayed on a different model, a different project, or a different engineer's session — and produce meaningful results because it carries the engineering understanding, not just the keystroke sequence.

### The routine execution cycle
```
prompt_def artifact (ignition)
        ↓
render_prompt → instantiated prompt with current context
        ↓
generate_fabric → current model state injected
        ↓
KP reasons over model + knowledge artifacts
        ↓
apply_model_patch → model updated
write_artifact / add_log_entry → knowledge base updated
        ↓
New knowledge artifacts → seed next routine execution
```

### Connection to the engine analogy
In engine terms, a routine is a **pre-configured ignition sequence** — the timing, fuel mixture, and compression ratio set in advance so the power stroke fires reliably every time. The prompt is the spark plug. The knowledge artifacts are the fuel mixture. The model is the compression chamber. The routine orchestrates all three.

### Implications for implementation
The `render_prompt` tool in the artifact repo already supports this pattern. The next implementation step is:
1. Define `prompt_def` artifacts for common SE tasks (capability definition, function naming, exchange review, FMEA seeding, property value population)
2. Each `prompt_def` takes model fabric and knowledge context as Jinja2 template variables
3. Rendered prompts are passed to the KP which executes the reasoning and patch cycle
4. Results are written back as knowledge artifacts, which enrich future prompt_def executions

### For the paper
> *Building a routine is about leveraging the artifacts of prompts, knowledge, and models. A routine is not a recording of past interactions — it is a synthesis of engineering intent, accumulated rationale, and current model state. When these three artifact types are combined and replayed, the result is not a repetition of what was done before but an application of what was learned before to whatever state the model is in now. That is the difference between automation and intelligence.*

---

## 2026-06-16T20:26:15Z — note

## NOTE: Upcoming capability — artifact web viewer with embedded URLs in work log

**Date:** 2026-06-16
**Source:** Cousin (Claude Code) — enhancements ready to test 2026-06-17
**Status:** Pending test session

### Capability description
The cousin has implemented two related enhancements:

1. **Artifact web viewer** — a browser-based viewer for knowledge artifacts. Renders artifact content (text, table, log_book, routine_def) as a formatted readable document rather than raw file content. Accessible via URL.

2. **Embedded URLs in log entries** — artifact references in work log entries will include a direct URL to the web viewer, allowing the engineer to click from the log directly to the rendered artifact.

### Why this matters
Currently the artifact knowledge base exists as files in the GitHub repo — accessible but not immediately readable without cloning or navigating the repo structure. The web viewer makes artifacts first-class readable documents that can be:
- Shared with stakeholders who don't have repo access
- Linked from requirements tools (Polarion, Teamcenter) as living references
- Embedded in review board findings as clickable evidence
- Accessed from mobile without a git client

### Connection to CSID
The web viewer is a natural complement to the CSID pipeline. When a routine produces a FMEA artifact, the CSID completion notification can include a direct URL to the rendered FMEA. Engineers receive a link, click it, read the finding — no repo navigation required. This closes the last gap between automated pipeline output and engineer consumption.

### Connection to routine_def
The `routine_def` output specification already includes `artifact_id` in the post-execution summary. With the web viewer, that artifact_id becomes a clickable URL. The `report` section of the routine can emit: "FMEA generated — view at https://kp.viewer/artifacts/{{ fmea_artifact.artifact_id }}"

### Test plan for 2026-06-17
1. Confirm web viewer renders text, table, and log_book artifact types correctly
2. Confirm embedded URL in log entry is clickable and resolves to correct artifact
3. Test with FMEA artifact (09e17c34) and routine_def spec (6d9342f2) from today's session
4. Test with work log (8b3aa13b) — log_book rendering with entry types and timestamps
5. Confirm URL is stable across artifact updates (same artifact_id, new content version)

### Potential issue to watch
The work log artifact (`8b3aa13b`) has been written to both `master` and `main` branches at different points in the Road Grader sessions. The web viewer URL should resolve to the correct branch — confirm branch disambiguation is handled.

---

## 2026-06-16T20:28:29Z — observation

## OBS-009 · Artifact web viewer enables reflection and artifact-driven planning — closing the OODA loop

**Source:** Engineer reflection, 2026-06-16
**Category:** Workflow insight — capability impact
**Related:** Web viewer note, CSID vision, OBS-006 (progression)

### Observation
The artifact web viewer capability — URLs embedded in log entries, artifacts rendered as readable documents — does more than improve accessibility. It closes the **OODA loop** (Observe, Orient, Decide, Act) for systems engineering.

### The OODA loop in MBSE

| OODA phase | Without web viewer | With web viewer |
|---|---|---|
| **Observe** | Navigate repo, clone, read raw YAML | Click URL → rendered artifact in browser |
| **Orient** | Reconstruct context from memory and notes | Work log timeline with linked artifacts as the complete context |
| **Decide** | Based on reconstructed understanding — incomplete | Based on full visible artifact record — current and accurate |
| **Act** | Next session starts from partial context | Next session starts from complete artifact-driven plan |

### Reflection becomes effortless
Without the viewer, reflection requires effort — cloning, navigating, reading raw files. With it, reflection is as natural as reading a document. The engineer opens the work log, sees the milestone timeline, clicks the FMEA, reads the top RPN items, clicks the routine_def spec, sees what routines are available. The full engineering record is readable in minutes.

When reflection is effortless, it happens more often. More frequent reflection means faster course correction, better planning, and less work lost to misremembered context.

### Planning becomes artifact-driven
The web viewer transforms artifacts from outputs into inputs to the planning process:

- **FMEA artifact** → "which gaps need property values? which RPN items need requirements?"
- **Routine_def library** → "which routines do we run next? what's missing from the library?"
- **Work log** → "what's open? what decisions need to be revisited? what's the next milestone?"
- **CSID pipeline spec** → "which stages are implemented? what's the deployment gate status?"

This is qualitatively different from planning based on memory or meeting notes. The artifacts are the plan — they encode current state, open items, and next steps in a form that both the engineer and the KP can read and act on.

### The planning loop
```
Artifact web viewer (reflect on current state)
        ↓
Engineer identifies next priority from artifacts
        ↓
KP executes routine or modeling session
        ↓
New artifacts produced (linked in log)
        ↓
Artifact web viewer (reflect on updated state)
```

This is the OODA loop running on engineering artifacts rather than battlefield intelligence. The faster the loop turns, the more responsive the engineering process.

### Connection to CSID
In the CSID pipeline, the web viewer is the engineer-facing dashboard. Pipeline outputs (integrity reports, FMEA refreshes, review findings) are not buried in repo files — they are immediately readable documents linked from the pipeline completion notification. The engineer observes the pipeline output, orients on the findings, decides what to fix, and acts on the model. One loop turn per commit.

### For the paper
> *The artifact web viewer is not a cosmetic improvement — it is the interface through which the knowledge flywheel becomes visible. When stored momentum can be seen and read effortlessly, reflection becomes a natural part of the engineering workflow rather than a periodic overhead. And when reflection is continuous, planning becomes artifact-driven — grounded in current state rather than reconstructed from memory. The OODA loop closes. The flywheel turns faster.*

---

## 2026-06-16T20:30:19Z — observation

## OBS-010 · Deming quality cycles as the theoretical foundation for CSID and KP workflow

**Source:** Engineer, 2026-06-16
**Category:** Theoretical foundation — paper framing
**Related:** OBS-009 (OODA loop), CSID vision, flywheel

### The Deming connection
W. Edwards Deming's core insight: quality is not inspected in at the end — it is built in through continuous improvement cycles. His PDCA cycle (Plan, Do, Check, Act) is the engine of that philosophy. The KP workflow and CSID are a direct application of Deming's principles to systems engineering.

### PDCA mapped to CSID

| PDCA | CSID equivalent | KP artifact |
|---|---|---|
| **Plan** | Define routine_def — declare inputs, outputs, variables, pre-flight checks | `routine_def` artifact |
| **Do** | Execute the routine — model, patch, analyze, generate | Model commits + KP session |
| **Check** | Run CSID pipeline — integrity check, traceability, FMEA refresh, review board | Pipeline stage outputs |
| **Act** | Engineer acts on findings — fixes model, adds requirements, updates property values | Next model commit |

Each commit turns one PDCA cycle. Each cycle improves the model. The knowledge artifacts are the Check output — the measurement that drives the Act.

### Why Deming's philosophy fits MBSE so well
Deming argued that most defects are caused by the system, not the worker — and that improving the system requires data, not blame. In MBSE:
- Most model defects (unnamed exchanges, missing allocations, wrong types) are caused by the workflow, not the engineer — they are systematic gaps in the modeling process
- The CSID pipeline provides the data (integrity reports, FMEA, traceability gaps) that exposes the systematic gaps
- The routine library is the improved system — encoding the right way to do each task so it doesn't depend on individual memory or expertise

### The quality cycles the web viewer opens

The artifact web viewer and embedded URLs open the door to multiple Deming-inspired quality cycles operating at different cadences:

| Cycle | Cadence | PDCA scope |
|---|---|---|
| **Commit cycle** | Every model commit | PDCA on model integrity — pipeline runs, findings logged |
| **Session cycle** | Every KP session | PDCA on knowledge quality — artifacts reviewed, gaps identified, next session planned |
| **Capability cycle** | Every capability completed | PDCA on requirements — capability → functions → exchanges → FMEA → requirements closure |
| **Baseline cycle** | Every CSID-verified baseline | PDCA on the system — full pipeline pass defines a quality gate |
| **Routine improvement cycle** | Every new routine authored | PDCA on the process — routine_def refined based on execution experience |
| **Paper/demo cycle** | Each paper draft or demo run | PDCA on the argument — findings from demo inform next iteration of the theory |

### Deming's system of profound knowledge applied to MBSE
Deming identified four components of profound knowledge:
1. **Appreciation for a system** — the model IS the system representation; the KP makes the system visible and reasoned over
2. **Knowledge about variation** — FMEA RPN scores quantify variation; property value min/max bounds define acceptable variation
3. **Theory of knowledge** — the knowledge flywheel IS a theory of knowledge accumulation and application
4. **Psychology** — the multi-role review board (OBS-004) addresses the human dimension of engineering quality

### For the paper
Positioning the KP and CSID within Deming's framework gives the paper a rigorous theoretical foundation that resonates with quality-conscious engineering organizations — particularly in automotive, aerospace, and heavy equipment sectors (all of which are Deming country).

> *Deming taught us that quality is built in, not inspected in. The SE Knowledge Partner and CSID apply this principle to systems engineering: quality is built into the model through continuous cycles of planning, doing, checking, and acting — driven by a routine library that encodes the right way to engineer, a knowledge base that accumulates the evidence of each cycle, and a web viewer that makes the accumulated evidence visible enough to reflect and act on. The flywheel turns. The system improves.*

### The door the web viewer opens
Every quality cycle requires a Check phase — a measurement that is visible, readable, and actionable. Without the web viewer, the Check phase requires effort (navigate repo, clone, read files). With it, Check is as natural as opening a browser tab. When Check becomes effortless, all the cycles turn faster — commit cycle, session cycle, capability cycle, baseline cycle, all of them. Deming's prescription becomes practical.

---

## 2026-06-16T23:22:28Z — observation

## OBS-011 · Routines as CNC machines — autonomous execution, engineer parallelism, and time-study justification

**Source:** Engineer, 2026-06-16
**Category:** Workflow analogy — economic justification
**Related:** routine_def specification, CSID vision, Deming (OBS-010)

### The CNC analogy
A CNC (Computer Numerical Control) machine transformed manufacturing the same way routines transform systems engineering:

- **Before CNC:** A machinist stands at the machine, makes every cut manually, applies judgment at each step, cannot do anything else while the part is being made
- **After CNC:** The machinist programs the job, loads the stock, presses start, and walks away to do other work. The machine runs the program. The machinist returns to inspect and act.

A `routine_def` is the CNC program for a systems engineering task. The KP is the CNC machine. The engineer is the machinist who programs it, starts it, and returns to inspect the output.

### What this changes for the engineer

| Dimension | Manual SE task | Routine-executed SE task |
|---|---|---|
| Engineer presence | Required throughout | Required only at start and end |
| Parallelism | One task at a time | Multiple routines running simultaneously |
| Consistency | Varies with engineer skill and attention | Deterministic — same routine, same output structure |
| Interruption cost | High — context lost if interrupted | Zero — routine runs to completion regardless |
| Auditability | Depends on engineer documentation discipline | Built-in — artifact outputs are the audit trail |
| Repeatability | Requires re-learning | Instant — re-run the routine |

### Time studies as economic justification
The engineer noted that time studies were used to justify CNC adoption in manufacturing. The same methodology applies to routine adoption in MBSE:

**Manual FMEA generation (Road Grader Steering Control):**
- Identify all exchanges in chain: ~45 min
- Research failure modes per exchange: ~3 hours
- Write FMEA table with S/O/D/RPN: ~2 hours
- Document gaps and recommended actions: ~1 hour
- **Total: ~6.5 hours active engineer time**

**Routine-executed FMEA (today's session):**
- Trigger: "run FMEA for Steering Control" — 30 seconds
- Execution: KP generates fabric, analyzes 21 failure modes, writes artifact — ~8 minutes
- Engineer review and validation: ~20 minutes
- **Total: ~30 minutes active engineer time, ~8 minutes unattended**

**Time study result: ~13× reduction in active engineer time per FMEA**

The engineer can use those 6 hours for higher-value work — design decisions, stakeholder engagement, system architecture — while the routine runs unattended.

### Parallelism — the CNC shop floor effect
A CNC shop floor doesn't run one machine at a time. Multiple machines run simultaneously, each on a different part, while the machinist moves between them. The CSID pipeline is the SE equivalent:

- Stage 1 (integrity check) runs while engineer is in a design meeting
- Stage 2 (traceability check) runs while engineer is updating requirements
- Stage 3 (FMEA refresh) runs while engineer is reviewing stakeholder feedback
- Engineer returns to find all three complete, linked in the work log, readable via web viewer

The engineer's scarce cognitive resource — focused attention — is applied only where it cannot be replaced: judgment, decisions, stakeholder communication, creative synthesis.

### The routine library as the CNC program library
A mature CNC shop maintains a library of proven programs — tested, refined, ready to run. Each program encodes institutional knowledge about how to make a specific part. The routine library is the same thing for systems engineering:

- `fmea_from_functional_chain` — proven, run once on Road Grader, ready to run on any project
- `model_integrity_check` — to be authored, then runs on every project indefinitely
- `requirements_from_capability` — encodes the institutional knowledge of how to write good requirements

New engineers on the team don't need to know how to generate an FMEA from scratch — they run the routine. The institutional knowledge is in the program, not the individual.

### The Deming connection
Deming would recognize this immediately. CNC adoption in manufacturing was driven by the same forces he described:
- Reduce variation (consistent routine output vs. variable manual output)
- Build quality in (routine includes pre-flight checks and post-execution validation)
- Improve the system (routine library gets better with each execution — the program is refined based on results)

### For the paper
> *A routine_def is the CNC program for a systems engineering task. Before routines, the engineer stands at the task for its full duration — present, attentive, unreplaceable. After routines, the engineer programs the task, starts it, and applies their attention elsewhere. The KP runs the program. The engineer returns to inspect and act. This is not automation replacing the engineer — it is the engineer's judgment, encoded once and applied reliably many times, freeing their attention for the work that cannot be encoded: the decisions, the synthesis, the creative leaps that no routine can make.*

### Economic argument for adoption
Time studies like those used to justify CNC adoption can justify routine adoption in MBSE. A single FMEA routine justified by a 13× time reduction, run quarterly on a 5-capability model, saves approximately 150 engineer-hours per year per project. A library of 10 routines running as a CSID pipeline represents a transformation in SE productivity comparable to what CNC represented for manufacturing.

---

## 2026-06-16T23:47:08Z — observation

## OBS-012 · GitHub Copilot MCP + GitHub Actions as CSID pipeline trigger mechanism

**Source:** Engineer, 2026-06-16
**Category:** Implementation pathway — CSID automation
**Related:** CSID vision, routine_def specification, OBS-011 (CNC analogy)

### The question
GitHub Copilot now supports MCP. Can a routine be fired automatically when a model change is committed to master?

### The answer — yes, via two complementary pathways

---

### Pathway 1 — GitHub Actions + MCP server call (most direct)

GitHub Actions already triggers on push to master. The workflow calls the capella-fabric and artifact-repo MCP servers directly via HTTP, executing the routine_def without requiring a human to open a chat session.

```yaml
# .github/workflows/csid_pipeline.yml
name: CSID Pipeline
on:
  push:
    branches: [master]
    paths:
      - 'Road_Grader_Front_Axel_Assembly/**/*.capella'
      - 'Road_Grader_Front_Axel_Assembly/**/*.aird'

jobs:
  csid:
    runs-on: ubuntu-latest
    steps:
      - name: Stage 1 — Model Integrity Check
        run: |
          curl -X POST https://mcp.innovatingwithcapella.com/mcp \
            -H "Authorization: Bearer ${{ secrets.CAPELLA_MCP_PAT }}" \
            -d '{
              "routine": "model_integrity_check",
              "variables": {
                "model_repo_url": "${{ github.repository }}",
                "commit_sha": "${{ github.sha }}"
              }
            }'

      - name: Stage 2 — FMEA Refresh
        run: |
          curl -X POST https://mcp.innovatingwithcapella.com/mcp \
            -H "Authorization: Bearer ${{ secrets.CAPELLA_MCP_PAT }}" \
            -d '{
              "routine": "fmea_from_functional_chain",
              "variables": {
                "functional_chain_name": "Steering Control",
                "artifact_package": "Road_Grader_Front_Axel_Assembly",
                "output_branch": "main"
              }
            }'
```

This is pure CI/CD — no human in the loop. The routine runs, artifacts are written to main, URLs are embedded in the work log. Engineer opens the web viewer to see results.

**What's needed to implement:**
- `routine_def` execution endpoint on the capella-fabric or a new `routine-runner` MCP server
- GitHub Actions workflow file in the repo
- Secrets configured for MCP PAT

---

### Pathway 2 — GitHub Copilot + MCP (interactive, commit-time)

GitHub Copilot with MCP support can surface the KP directly in the IDE at commit time. When the engineer commits model changes in VS Code or Eclipse with Copilot:

1. Copilot detects the changed `.capella` files
2. Copilot invokes the capella-fabric MCP to check model integrity
3. Copilot presents findings in the IDE: "3 unnamed exchanges detected. Run naming routine?"
4. Engineer approves → routine fires → artifacts written → URL presented in IDE

This is the **shift-left** pattern from software CI applied to MBSE — catching issues at commit time in the IDE rather than after push to remote.

**What's needed:**
- Copilot MCP extension configured with capella-fabric and artifact-repo servers
- A lightweight `pre_commit_check` routine_def that runs fast (integrity only, no FMEA)
- Copilot prompt template that presents findings clearly in IDE context

---

### Pathway 3 — OBEO TeamForCapella webhook (future)

When the OBEO tighter integration (OBS-001) is implemented, TeamForCapella's model server could fire a webhook on every model save — not just on git commit. This would enable:

- Sub-commit granularity triggering (check on save, not just on push)
- Live integrity checking as the engineer models
- Real-time feedback in the Capella diagram view

This is the fully integrated vision — the CNC machine running while the engineer is still at the workbench, flagging issues before the commit rather than after.

---

### Recommended implementation sequence

| Step | Action | Effort | Value |
|---|---|---|---|
| 1 | Add `routine_def` execution to capella-fabric MCP (cousin) | Medium | Enables all pathways |
| 2 | Author `model_integrity_check` routine_def | Low | Immediate CSID Stage 1 |
| 3 | Add GitHub Actions workflow to Road Grader repo | Low | Pathway 1 live |
| 4 | Test FMEA refresh on model commit | Low | CSID Stage 3 live |
| 5 | Configure Copilot MCP for pre-commit check | Medium | Pathway 2 live |
| 6 | OBEO integration | High | Pathway 3 (future) |

### Connection to Deming
Each pathway implements PDCA at a different granularity:
- Pathway 3 (OBEO) — PDCA on every save — tightest loop
- Pathway 2 (Copilot) — PDCA on every commit attempt — shift-left
- Pathway 1 (Actions) — PDCA on every pushed commit — current CI/CD pattern

Deming would say: the tighter the loop, the faster the improvement. Start with Pathway 1 (achievable now), evolve toward Pathway 3 (tightest loop).

### For the paper
> *The question is not whether routines can be triggered automatically on model change — they can, via GitHub Actions today. The question is how tight the feedback loop should be. GitHub Actions gives you PDCA per commit. GitHub Copilot with MCP gives you PDCA per save attempt. OBEO integration gives you PDCA per model edit. Deming's prescription is clear: tighten the loop. The technology is ready. The routine library is the remaining dependency.*

---

## 2026-06-17T15:55:59Z — observation

## OBS-013 · The artifact repository is a context engineering system for MBSE

**Source:** Engineer, 2026-06-16
**Category:** Architectural framing — paper thesis
**Related:** OBS-007 (three primitives), OBS-008 (artifacts as routine source), CSID vision

### The insight
Context engineering is an emerging discipline in AI practice that is more precise than prompt engineering. Prompt engineering focuses on how you phrase the question. Context engineering focuses on what information surrounds the question when the AI reasons over it.

The KP artifact repository is a context engineering system. It does not make prompts better — it makes the context richer, more structured, and more current. Every artifact written to it is engineered context: curated, versioned, and structured to maximize the reasoning power of the AI in every future session.

### What the KP receives as context in each session
When the KP starts a session, it does not just receive a prompt. It receives:
- **Model fabric** — what exists now (current state, via fabric generation)
- **Work log** — what has been done and decided (history, via log_book)
- **FMEA artifacts** — what the risks are (analysis, via text artifacts)
- **Design decisions** — why things are the way they are (rationale, via decision entries)
- **Routine_defs** — what patterns are available (process, via routine_def artifacts)
- **Issues log** — what doesn't work yet (constraints, via issue entries)

Each of these is engineered context — not raw data, not a chat log, but curated, structured, named artifacts that have been refined through the curation process described in the central paper thesis.

### The architectural layer map

| Layer | Engineering discipline |
|---|---|
| Prompt template in routine_def | Prompt engineering — how to ask |
| Artifact repo content | Context engineering — what to reason over |
| Fabric generation | Context compression — making model content LLM-readable |
| CSID pipeline | Context freshness — keeping artifacts current on every commit |
| Web viewer | Context accessibility — making context readable without friction |
| Flywheel | Context accumulation — momentum stored between sessions |

### Why context engineering is more powerful than prompt engineering
A better prompt with poor context produces mediocre reasoning. A simple prompt with rich context produces excellent reasoning. The Road Grader sessions demonstrated this repeatedly — the KP's most valuable outputs (the FMEA, the design decisions, the architectural observations) came not from sophisticated prompting but from rich context: the model fabric, the work log history, the CAD reference, the prior decisions.

The artifact repo is where that context lives, grows, and is maintained. It is the fuel in the engine. The prompt is merely the ignition.

### Connection to Deming
Context engineering is a quality discipline — it is the systematic improvement of the information environment in which reasoning occurs. Deming would recognize it: you cannot improve the output without improving the system that produces it. The system here is the context. Improving the context improves every future reasoning cycle automatically.

### For the paper
> *The artifact repository is not a document store — it is a context engineering system. Every artifact written to it is engineered context: curated, structured, and versioned to maximize the reasoning power of the AI in every future session. Prompt engineering asks how to phrase the question better. Context engineering asks what information should surround the question when it is asked. The KP artifact repository answers the second question. The prompt is the ignition. The context is the fuel. Context engineering is what makes the fuel combustible.*

### Emerging terminology alignment
"Context engineering" is gaining traction in the AI practitioner community as the practice of deliberately designing and maintaining the information environment that an LLM reasons over. Positioning the KP knowledge base under this term connects the paper to current AI discourse while remaining grounded in systems engineering practice — a bridge between the two communities the paper needs to reach.

---

## 2026-06-17T18:46:13Z — observation

## OBS-014 · Artifact store reduces chat session to a trigger — knowledge lives in the repo, decisions live in the chat

**Source:** Engineer, 2026-06-17 — after Camber Control FMEA routine execution
**Category:** Foundational validation — context engineering thesis confirmed in practice

### The observation
"I am actually shocked on how well that worked. The artifacts store really reduces the chat session content nicely."

This reaction captures a fundamental shift in the role of the chat session. The Camber Control FMEA was produced with a single message: "run routine fmea_from_functional_chain with functional_chain_name = Camber Control." No setup. No explanation. No context reconstruction. 21 FMEA rows, 5 gaps identified, cross-chain analysis complete, artifact written, work log updated.

### Why it worked — what the artifact store provided
The routine didn't need a long conversation because the knowledge was already in context:
- **Model fabric** — current chain structure, all 15 exchanges, allocated components
- **Prior FMEA** — Steering Control baseline for cross-reference and shared component identification
- **Routine_def** — the method, S/O/D scoring guidance, output structure, prompt template
- **Work log** — engineering history, design decisions, prior session context

None of that had to be re-explained. The artifact store held it. The chat session was just the ignition.

### What this changes about the chat session
The chat session is no longer the place where knowledge lives. It is the place where decisions get made.

| Before artifact store | After artifact store |
|---|---|
| Chat session carries all context | Artifact store carries all context |
| Long setup to establish shared understanding | Single trigger to execute |
| Knowledge reconstructed each session | Knowledge accumulated across sessions |
| Session is the work | Session is the decision point |
| Long sessions required for complex outputs | Complex outputs from minimal prompts |

### The deeper implication
This is the context engineering thesis (OBS-013) validated in practice. A two-word variable change — "Steering Control" to "Camber Control" — produced a completely new 21-row FMEA with cross-chain analysis because the context was rich enough to reason over without additional instruction.

The routine_def encoded the method once. The artifact store accumulated the context continuously. The chat session provided only what was new — the variable.

### The CNC analogy confirmed (OBS-011)
The engineer loaded the stock (Camber Control chain name), pressed start (sent the message), and received the finished part (FMEA artifact + work log entry). The machine ran without supervision. The engineer's reaction — "shocked on how well that worked" — is exactly the reaction a machinist has the first time they watch a CNC program run a complex part unattended.

### For the paper
> *The artifact store doesn't just reduce the chat session — it transforms it. The chat is no longer where knowledge is built; it is where decisions are made. When the artifact store holds the method, the history, the model, and the prior analysis, a single trigger produces a complex output that would previously have required an extended collaborative session. This is the CNC machine running. The engineer loads the variable, presses start, and the knowledge engine delivers the finished artifact. The chat session becomes the control panel, not the workshop.*

### Quantified evidence from this session
- Steering Control FMEA: required full session, fabric review, interactive topology discussion, multiple exchange naming patches, then FMEA generation
- Camber Control FMEA: required one message — "run routine with functional_chain_name = Camber Control"
- Output quality: equivalent — 21 rows each, comparable analytical depth, cross-chain enrichment added automatically

The difference is the accumulated artifact store between the two executions. That is the flywheel turning.

---

## 2026-06-17T23:30:39Z — observation

## OBS-015 · Microsoft Teams / SharePoint as binary artifact store and stakeholder delivery channel

**Source:** Engineer, 2026-06-17
**Category:** Integration pathway — enterprise deployment
**Related:** ISSUE-001 (binary upload), routine_def spec, CSID vision

### The opportunity
Siemens and Penn State University both use Microsoft Teams as their collaboration platform. Teams is built on SharePoint as its file store. This creates a natural integration path for KP binary artifacts (.docx, .xlsx, .pdf) that complements the text-based artifact repo without requiring changes to the core architecture.

### The integration architecture

```
KP generates .docx / .xlsx (computer tools)
        ↓
Upload to SharePoint via Microsoft Graph API MCP
        ↓
SharePoint stores file in Teams channel document library
        ↓
Artifact repo stores reference artifact with SharePoint URL
        ↓
Work log entry includes SharePoint URL (clickable via web viewer)
        ↓
Stakeholders access via Teams — no repo access required
```

### Why this works cleanly
- **Text stays in git** — the knowledge base (FMEA, decisions, routines) remains in the artifact repo as readable, diffable, versionable text
- **Binary goes to SharePoint** — generated .docx, .xlsx, .pdf deliverables live where stakeholders already work
- **URLs connect the two** — artifact repo reference entries link to SharePoint files; Teams channels link back to the web viewer for the source artifact
- **No new infrastructure** — both organizations already have Teams/SharePoint licensed and deployed

### Microsoft Graph API MCP
Microsoft Graph API supports SharePoint file upload, Teams channel messaging, and document library management. An MCP server wrapping the Graph API would give the KP:
- `upload_to_sharepoint` — upload generated binary to a specified Teams channel document library
- `post_to_teams` — post a summary message to a Teams channel with links to the artifact and the SharePoint file
- `create_sharepoint_folder` — organize artifacts by project, milestone, or date

### Routine pattern — artifact to Teams delivery

```yaml
routine_def:
  id: deliver_artifact_to_teams
  variables:
    - artifact_name       # e.g. "FMEA — Steering Control"
    - output_format       # docx / xlsx / pdf
    - teams_channel       # target Teams channel
    - sharepoint_library  # document library path
  steps:
    1. Read artifact from knowledge repo
    2. Render to output_format via computer tools
    3. Upload to SharePoint via Graph API MCP
    4. Post Teams message with summary + links
    5. Write reference artifact to knowledge repo with SharePoint URL
    6. Log milestone entry with delivery details
```

### The stakeholder experience
An engineer runs the FMEA routine → artifact written to knowledge repo → delivery routine triggered → `.docx` appears in the Teams channel document library → stakeholders receive a Teams notification with a summary and links → they click the document in Teams, no repo navigation required.

This is the CSID pipeline completing its last mile — from model commit to stakeholder-readable deliverable, fully automated.

### For the paper
> *The knowledge base lives in git — readable, diffable, versionable. The deliverables live in SharePoint — accessible, familiar, integrated with the tools stakeholders already use. The KP bridges the two: generating binary outputs from curated text artifacts and delivering them to Teams channels via the Microsoft Graph API. The systems engineer never leaves their workflow. The stakeholder never has to learn a new tool. The knowledge flywheel turns, and the output lands where it needs to be.*

### Next steps for cousin
1. Investigate Microsoft Graph API MCP server options — open source implementations exist
2. Define `deliver_artifact_to_teams` routine_def
3. Test with FMEA — Steering Control → Teams channel in a Siemens or PSU environment
4. Consider bi-directional sync — stakeholder comments in Teams feeding back as observations in the knowledge repo

---

## 2026-06-17T23:35:12Z — decision

## DECISION: Next routine — requirements management, replicating existing Jupyter notebook

**Date:** 2026-06-17
**Status:** Planned — next development session
**Significance:** First routine_def that directly replaces a coded Jupyter notebook

### Decision
The next `routine_def` to be authored will replicate an existing Jupyter notebook that works with requirements in a Capella model on a separate project. This is a deliberate head-to-head comparison — same task, notebook vs. routine_def.

### Why this is significant
The FMEA routine was a net-new task — no prior notebook existed to compare against. The requirements routine will be the first direct replacement of a coded artifact with a declarative routine_def. This tests the core claim in the routine_def specification: that routine_defs are a superior alternative to Jupyter notebooks for MBSE tasks.

### What to measure during development

| Dimension | Jupyter Notebook | routine_def | Expected result |
|---|---|---|---|
| Lines of code | Count existing notebook | Count prompt template | Notebook >> routine_def |
| Dependencies | List pip requirements | None | Notebook has dependencies |
| Model schema knowledge | Hardcoded in code | Abstracted via fabric | Notebook brittle, routine adaptive |
| Authoring skill required | Python + capellambse API | YAML + natural language | Routine accessible to non-coders |
| Maintenance on API change | Code rewrite | Prompt update | Routine much lower maintenance |
| Output quality | Fixed by code logic | Adaptive via reasoning | Routine potentially richer |
| Execution time | Measure | Measure | TBD — notebook may be faster |
| Reusability across projects | Low — hardcoded paths | High — variables parameterize | Routine wins |

### Requirements task scope (to be confirmed with engineer)
Typical requirements notebook tasks in Capella include:
- Extract all requirements from a model layer (SA/LA/PA)
- Check requirement coverage — which functions/components have no traced requirement
- Generate a requirements traceability matrix (RTM)
- Identify orphaned requirements (no model element traces to them)
- Export requirements to a structured format (Word, Excel, Polarion import)
- Import requirements from an external source and allocate to model elements

The engineer will specify which of these the existing notebook covers. The routine_def will replicate that scope exactly, then the comparison is made.

### Connection to CSID
A requirements routine is a natural CSID Stage 2 pipeline step — traceability verification on every model commit. Once proven as a routine_def, it slots directly into the pipeline:

```
Stage 1 — Model integrity check
Stage 2 — Requirements traceability check  ← this routine
Stage 3 — FMEA refresh
Stage 4 — Review board
Stage 5 — Deployment gate
```

### Connection to paper
The notebook-to-routine comparison is the strongest possible evidence for the routine_def architectural argument. If a requirements task that required a coded Python notebook can be replicated by a YAML + natural language routine_def — and produces equivalent or better output — the case for routine_defs as the SE CI/CD primitive is made concretely.

### Note on separate project
The requirements routine will be authored against a different project model. This also tests the routine_def's portability claim — that a routine written for one project (Road Grader) can be applied to another project with only variable changes. The `artifact_package` and `model_repo_url` variables should be the only things that change.

---

## 2026-06-17T23:37:46Z — decision

## DECISION: Requirements routine scope — extraction and impact analysis of needs against baseline requirements

**Date:** 2026-06-17
**Related:** Previous decision — notebook-to-routine replacement

### Task definition
The requirements routine will replicate and extend a Jupyter notebook that performs two tasks:

1. **Extraction** — pull requirements from the Capella model (from a specified layer or module)
2. **Impact analysis** — given a set of new or changed needs, determine which baseline requirements are impacted, added, modified, or unaffected

This is widely recognized as one of the most tedious tasks in systems engineering. The notebook automates the mechanical extraction and comparison. The routine_def will replicate this and add the layer of interpretation that code cannot provide.

### Why this task is so painful manually
A requirements impact analysis typically requires an engineer to:
- Extract all current baseline requirements (dozens to hundreds)
- Read each new or changed need
- Manually trace which baseline requirements relate to each need
- Classify the impact: New requirement needed / Existing requirement modified / No impact
- Document the rationale for each classification
- Produce a matrix or report for review board

On a typical system with 200 baseline requirements and 20 new needs, this takes 2-3 days of focused engineer time. The Jupyter notebook reduces the mechanical extraction and comparison to minutes — but still produces a matrix that requires manual interpretation. The routine_def adds the interpretation.

### What the routine_def adds over the notebook

| Capability | Jupyter Notebook | routine_def |
|---|---|---|
| Extract requirements from model | ✅ | ✅ |
| Compare needs against baseline | ✅ (string matching / semantic similarity) | ✅ (LLM semantic reasoning) |
| Classify impact (New/Modified/None) | ✅ (rule-based) | ✅ (reasoning-based) |
| Explain WHY each requirement is impacted | ❌ | ✅ — natural language rationale |
| Identify implied requirements not in baseline | ❌ | ✅ — gap reasoning |
| Flag contradictions between needs and baseline | ❌ | ✅ — semantic conflict detection |
| Suggest requirement text for new/modified items | ❌ | ✅ — draft language generation |
| Cross-reference with functional chain coverage | ❌ | ✅ — model-aware analysis |
| Output to artifact repo + work log | ❌ | ✅ |

### The routine_def structure (planned)

```yaml
routine_def:
  id: requirements_impact_analysis
  name: "Requirements Impact Analysis"
  variables:
    - needs_source         # artifact name or inline list of new/changed needs
    - baseline_module      # Capella requirements module name to analyze against
    - model_phase          # SA / LA / PA
    - artifact_package     # target package for output
    - output_format        # text / docx / xlsx

  inputs:
    - needs artifact       # the set of new or changed needs
    - baseline requirements # extracted from model via fabric

  outputs:
    - Impact Analysis Report artifact
      - Full impact matrix (need × requirement × classification × rationale)
      - New requirements draft (suggested text for gaps)
      - Modified requirements (suggested updated text)
      - Unaffected requirements (confirmed no change needed)
      - Summary statistics
    - Work log milestone entry

  prompt_template: |
    Reason over the set of needs and baseline requirements.
    For each need:
    1. Identify all baseline requirements that relate to it
    2. Classify: Impacts (modify existing) / Gaps (new requirement needed) / None
    3. For Impacts: explain what must change and why
    4. For Gaps: draft the new requirement text as a shall statement
    5. Flag any contradiction between the need and existing requirements
    Cross-reference: which functional exchanges in the model would be
    affected by each modified or new requirement
```

### Why the KP adds unique value here
The notebook uses string matching or semantic similarity scoring to find related requirements. It cannot reason about *why* a need impacts a requirement, *what* the requirement text should say if modified, or *whether* the need contradicts an existing baseline assumption. The KP does all three — and does it in the language of systems engineering, not probability scores.

### Connection to Deming
Impact analysis is the Check phase of the requirements PDCA cycle. When a new need arrives:
- **Plan** — identify which requirements need to change
- **Do** — update the requirements
- **Check** — impact analysis (this routine)
- **Act** — update model allocations, functional chains, FMEA

The routine automates the Check phase that currently takes 2-3 days. The PDCA cycle turns in hours instead of weeks.

### For the paper
> *Requirements impact analysis is one of systems engineering's most tedious tasks — and one where AI reasoning adds the most value over code. A Jupyter notebook can extract and compare. Only an AI can explain why a requirement is impacted, draft the replacement text, and flag the contradiction that no one noticed was there. The routine_def makes this reasoning available on demand, triggered by a single message, producing a complete impact analysis artifact in minutes rather than days. This is the CNC machine running on the most intellectually demanding task in the requirements workflow.*

### Metric to capture during development
Time study comparison:
- Manual impact analysis (engineer estimate for the target project)
- Jupyter notebook execution time
- routine_def execution time
- Output quality comparison (matrix completeness, rationale depth, gap identification)

---

## 2026-06-18T00:50:52Z — milestone

## Milestone: Artifact web viewer deployed — https://artifacts.innovatingwithcapella.com/

**Date:** 2026-06-17
**Built by:** Cousin (Claude Code)

### Capability
Browser-based viewer for knowledge artifacts. Connect any artifact repo by providing:
- GitHub repository URL
- GitHub PAT (read access)
- Branch (master / main)

Viewer clones the repo and renders artifact content as formatted readable documents.

### Artifacts to test
- **KP Issues Log** (b8f58379) — knowledge_partner repo, master branch
- **Work Log — Road Grader** (8b3aa13b) — Road_Grader_Front_Axel_Assembly, main branch
- **FMEA — Steering Control** (09e17c34) — Road_Grader_Front_Axel_Assembly, main branch
- **FMEA — Camber Control** (56796e93) — Road_Grader_Front_Axel_Assembly, main branch
- **routine_def: fmea_from_functional_chain** (cd58ea00) — knowledge_partner, master branch
- **CSID Vision** (d6aeb784) — Road_Grader_Front_Axel_Assembly, main branch

### Connection to OODA and Deming
This capability closes the Check phase loop (OBS-009, OBS-010). Reflection on artifact content is now a browser tab, not a repo navigation exercise. The PDCA cycle tightens immediately.

### Next test
Verify embedded URLs in log entries resolve correctly to the viewer. If URL pattern is stable, all future log entries and routine output reports should include direct viewer links to produced artifacts.

---

## 2026-06-18T12:48:28Z — issue

## ISSUE-013 · routine_def schema not documented — field requirements discovered only through server validation errors

**Tool:** artifact_repo (`write_artifact` with type=routine_def)
**Status:** Open — documentation fix required
**First observed:** 2026-06-18, EBSD_300 requirements extraction session
**Severity:** Medium — authoring friction, no data loss

### Description
When authoring a `routine_def` artifact for the first time, the required schema fields had to be discovered iteratively through server-side validation errors. Three write-validate-fix cycles were required before the artifact passed validation. Required fields that were not apparent upfront included: `type` on each variable entry, `id` and `mcp_tool` on each resource entry, and `package` on each output entry.

### Details
First attempt returned:
```
routine_def YAML must have a top-level 'routine_def' key
```
Second attempt (after adding top-level key) returned:
```
variables[0] missing field: 'type'
variables[1] missing field: 'type'
variables[2] missing field: 'type'
variables[3] missing field: 'type'
resources[0] missing field: 'id'
resources[0] missing field: 'mcp_tool'
outputs[0] missing field: 'package'
```

### Impact
Three write-validate-fix cycles required. Token and time overhead. High friction for first-time routine authors. Risk of authors giving up or writing malformed routines stored without validation.

### Root cause
No routine_def schema is documented in the KP system prompt (v4) or in any accessible SKILL.md. The `write_artifact` documentation in the system prompt lists content formats by artifact type but does not describe the internal structure required for `routine_def` YAML.

### Recommendation
Add a `routine_def` schema reference to the KP system prompt under the artifact-repo section. At minimum document: required top-level key (`routine_def:`), required variable fields (name, type, description, required, default), required resource fields (id, type, mcp_tool, description), `pre_flight` entry structure, `prompt_template` Jinja2 conventions, and required output fields (name, type, package, description, required). Include one minimal working example. This was resolved for the current session by iterative validation but should not require that process for future authors.

---

## 2026-06-18T12:48:40Z — issue

## ISSUE-014 · validate_routine_def reports only failures — no confirmation of passing fields

**Tool:** artifact_repo (`validate_routine_def`)
**Status:** Open — enhancement request
**First observed:** 2026-06-18, EBSD_300 requirements extraction session
**Severity:** Low — UX friction only

### Description
`validate_routine_def` returns only `errors` and `warnings`. It does not indicate which fields were checked and passed. During iterative authoring, after fixing one set of errors it was unclear whether previously-correct fields had regressed while fixing others.

### Current response structure
```json
{
  "valid": false,
  "errors": ["variables[0] missing field: 'type'", ...],
  "warnings": [...],
  "summary": { "id": "...", "variable_count": 4, ... }
}
```

### What is missing
A `passed` array alongside `errors` listing which fields/sections validated cleanly:
```json
{
  "valid": false,
  "errors": ["variables[0] missing field: 'type'"],
  "warnings": [],
  "passed": ["routine_def.id", "routine_def.name", "routine_def.version", "outputs[0].name", "outputs[0].description"],
  "summary": { ... }
}
```

### Impact
Iterative authoring requires re-running validation after every fix to confirm nothing regressed. Without a `passed` list, each validation response is read as "what is still broken" rather than "what is now correct." Adds cognitive load and extra validation round-trips.

### Recommendation
Extend the `validate_routine_def` response to include a `passed` list of verified-clean fields/sections. Alternatively, add a `--verbose` flag that shows the full field-by-field check result. The summary object already tracks counts (variable_count, resource_count, etc.) — the passed list is a natural extension of the same information.

---

## 2026-06-18T12:48:53Z — issue

## ISSUE-015 · pre_flight_checks vs pre_flight — field name inconsistency between system prompt and schema validator

**Tool:** artifact_repo (`validate_routine_def`, `write_artifact`)
**Status:** Open — system prompt fix required (partially resolved by system prompt update 2026-06-18)
**First observed:** 2026-06-18, EBSD_300 requirements extraction session
**Severity:** Medium — silent failure, no error surfaced

### Description
The KP system prompt v4 documented the pre-flight block as `pre_flight_checks`. The `validate_routine_def` server uses `pre_flight` as the correct field name and reports `"has_pre_flight": false` in the summary. Writing `pre_flight_checks` caused the validator to silently ignore the entire block — no error was raised, only the absence of `has_pre_flight: true` in the summary revealed the problem.

### Reproduction
```yaml
routine_def:
  id: my_routine
  pre_flight_checks:         # ← wrong field name per schema
    - check: "x != ''"
      error: "x required"
```
Validator summary: `"has_pre_flight": false` — no error raised.

### Why silent failure is dangerous
The author sees `valid: true` (or no pre_flight errors) and believes the pre-flight checks are in place. At execution time, no pre-flight validation occurs. A required variable can be empty and the routine proceeds rather than aborting cleanly.

### Resolution applied
System prompt updated 2026-06-18 to use `pre_flight` consistently. However:

### Remaining recommendation
The validator should emit a **warning** (not just silently pass) when it detects an unrecognised top-level key inside `routine_def` that is a near-miss for a known field. For example:
```
WARNING: Unrecognised field 'pre_flight_checks' — did you mean 'pre_flight'? This field will be ignored.
```
This would catch the silent failure case even if the system prompt documentation drifts again in a future version.

---

## 2026-06-18T12:49:08Z — issue

## ISSUE-016 · No dry-run / render mode for routine_def prompt_template — Jinja2 errors only surface at execution time

**Tool:** artifact_repo (`validate_routine_def`)
**Status:** Open — tooling enhancement required
**First observed:** 2026-06-18, EBSD_300 requirements extraction session
**Severity:** Medium — authoring risk

### Description
`validate_routine_def` checks structural completeness (required fields, variable entries, resource entries, output entries) but does not render the `prompt_template` with test variable values. Jinja2 syntax errors, wrong variable references, unclosed blocks, or malformed conditionals in the template will only surface at execution time — after the routine has been invoked against a live model.

### Example of a template error that would pass validation
```yaml
prompt_template: |
  Process {{ diagram_name }} in phase {{ phase }}.
  {% if artifact_name_prefx %}   ← typo: 'prefx' not 'prefix'
  Name: {{ artifact_name_prefx }} — {{ diagram_name }}
  {% endif %}
```
This passes `validate_routine_def` successfully. At execution time, the conditional evaluates to empty and the artifact name is wrong, with no error raised.

### Impact
Routine authors cannot verify template correctness before the routine is stored and executed. Complex templates with conditionals, loops, and variable references are particularly vulnerable. Errors may produce subtly wrong outputs (wrong artifact names, missing sections) rather than hard failures — making them harder to diagnose.

### Recommendation
Add a `render_routine_prompt` tool (analogous to `render_prompt` for `prompt_def` artifacts) that:
1. Accepts a `routine_def` artifact_id and a `variables` dict
2. Renders the `prompt_template` using Jinja2 with the supplied variable values
3. Returns the rendered string (or a Jinja2 error message if the template is malformed)

This allows authors to proof the template against realistic variable values before the routine is ever executed. Example call:
```
render_routine_prompt(
  artifact_id="434be3f3-...",
  package="EBSD_300",
  variables={"diagram_name": "[SAB] Context with Needs", "phase": "SA", "output_package": "EBSD_300"}
)
```
The rendered output should look like a complete, readable KP prompt — confirming the template works as intended.

---

## 2026-06-18T12:49:24Z — issue

## ISSUE-017 · Routine Execution Protocol implies Capella clone for all routines — should be explicitly conditional

**Tool:** KP System Prompt v4 — Routine Execution Protocol
**Status:** Open — system prompt clarification required
**First observed:** 2026-06-18, EBSD_300 routine_def authoring session
**Severity:** Low — behavioral ambiguity

### Description
The 10-step Routine Execution Protocol in the KP system prompt v4 defines Step 5 as:
> "For each declared resource — only if the routine declares it: capella_model_repo: clone_capella_repo + generate_fabric..."

The parenthetical "(Many routines have no Capella resource and skip this step entirely)" is correct but the overall framing of the protocol lists capella_model_repo as the primary resource example, which may lead KP to assume a model clone is always expected unless the routine explicitly opts out.

### Observed risk
When writing a routine that operates purely on artifact repo content (extraction, reporting, analysis of existing artifacts), a KP following the protocol literally might still attempt a capella clone if the resource type field uses any wording that could be interpreted as model-related — or might prompt the engineer to confirm whether a model clone is needed, adding unnecessary friction.

### Impact
Potential unnecessary clone operations (wasted time, extra API calls). Potential confusion for authors writing artifact-only routines who are not sure whether to declare a capella_model_repo resource.

### Recommendation
Make the branching logic in Step 5 more explicit:
```
Step 5 — Resource acquisition (conditional):
  IF routine declares resource type 'capella_model_repo':
    → clone_capella_repo on master + generate_fabric for target object
  IF routine declares resource type 'artifact_repo':
    → already connected via session; no additional clone needed
  IF routine declares no resources:
    → skip Step 5 entirely
  [No other resource type should trigger a model clone]
```
Additionally, add a documented enum of valid resource types (capella_model_repo, artifact_repo, external_api, none) so routine authors know what values are recognized and what behavior each triggers.

---

## 2026-06-18T12:49:41Z — issue

## ISSUE-018 · No standard convention for the post-execution engineer summary in routine prompt_templates

**Tool:** routine_def — prompt_template authoring convention
**Status:** Open — convention definition required
**First observed:** 2026-06-18, EBSD_300 requirements extraction session
**Severity:** Low — consistency gap across routine library

### Description
Each routine author currently hand-crafts the Step 8 (engineer summary) section of the prompt_template. There is no shared convention for what fields to always include, what format to use, how verbose to be, or how to present data quality observations. As the routine library grows, engineers will encounter inconsistent summary formats across different routines, degrading the predictability of the KP output experience.

### What the current routine (extract_needs_from_diagram_v1) includes in its summary
- Structured metadata table (diagram, phase, count, artifact ID, artifact name, package)
- Quick-reference markdown table (prefix, long name, relation targets)
- Data quality callout section (missing relations, placeholder text, duplicates, typos)

### What is undefined
- Which metadata fields are mandatory vs optional in all routine summaries
- Whether a markdown table is always appropriate or only for tabular outputs
- How to handle summaries for routines that produce non-tabular outputs (text, YAML, decisions)
- Whether the data quality callout is always expected or only when issues are found
- How to reference the artifact web viewer URL (once available — see ISSUE-016 test note)
- Whether the push commit SHA should always be included in the summary

### Impact
As the routine library grows to 10+ routines, engineers will not know what to expect from a routine summary. A routine that produces a terse summary after a large output will feel broken. A routine that produces a verbose summary for a simple output will feel noisy.

### Recommendation
Define a standard summary block convention in the KP system prompt or as a shared `prompt_def` artifact that routine authors include by reference. Suggested mandatory baseline fields for all routine summaries:

| Field | Always include |
|---|---|
| Routine ID | Yes |
| Input source (diagram, chain, artifact) | Yes |
| Count of primary objects processed | Yes |
| Artifact ID(s) written | Yes |
| Push commit SHA | Yes |
| Data quality flags (if any) | Yes — omit section only if none |
| Web viewer URL (when available) | Yes — once artifact viewer is live |

Allow per-routine extension beyond this baseline. The mandatory fields ensure any routine summary can be read and understood in the same way, regardless of which routine produced it.

---

## 2026-06-18T13:27:30Z — observation

OBS-016 · First end-to-end routine_def pipeline validated — model to artifact to viewer in a single session.

**Project:** EBSD_300
**Date:** 2026-06-18
**Routine:** extract_requirements_from_diagram_v1

### What happened
A routine_def was authored, generalised, and executed against two different diagrams in the same session:
1. [SAB] Context with Needs (SA phase, 3 requirements) — original target during authoring
2. [LAB] Requirements (LA phase, 45 requirements) — first generalised execution

The [LAB] Requirements run succeeded on the first attempt with no debugging. The engineer confirmed the resulting artifact was immediately readable in the artifact web viewer as a dashboard alongside other EBSD_300 artifacts.

### What this validates
Three things proved out together for the first time in a single session:

1. **Routine portability** — changing only diagram_name and phase variables redirected the full execution pipeline to a different diagram type and phase with no routine modification required. The parameterisation approach works.

2. **Routine reliability** — zero debugging cycles on the generalised execution. The routine held the method correctly; the variable held the target. This is the clean first-run behaviour that makes routines worth building.

3. **Viewer as dashboard** — the artifact web viewer presented the extracted requirements table alongside other EBSD_300 artifacts (SA needs, Extreme Impacted Requirements, work log) as an immediately readable dashboard. The engineer did not need to navigate the repo, clone, or parse raw files to read the output.

### Connection to prior observations
- OBS-008 (artifacts as routine source): the routine was seeded directly from the prior manual extraction session — same method, same CSV structure, now parameterised and replayable.
- OBS-011 (CNC analogy): one message, one clean artifact, no supervision. The machine ran.
- OBS-013 (artifact store as context engineering): the viewer presenting multiple artifacts as a dashboard is context engineering made visible — the accumulated knowledge base is now browsable without friction.
- OBS-014 (chat reduced to a trigger): the [LAB] Requirements extraction required a single invocation. The routine held everything else.
- OBS-009 (OODA loop via viewer): engineer observed output immediately in the viewer — oriented on the 45 requirements — ready to decide next action. One loop turn, sub-minute.

### Paper significance
This is the first complete demonstration of the full KP knowledge pipeline on a second project:
Model (Capella) → Routine (routine_def) → Artifact (table) → Viewer (dashboard)

Every link in that chain worked without manual intervention. The pipeline is not a prototype — it ran cleanly on real engineering content, producing a production-quality requirements artifact, immediately readable by the engineer.

The CNC machine ran. The flywheel is turning.

**References:** `434be3f3-e826-41cf-af6a-31875f5b6aed`

---

## 2026-06-18T13:34:19Z — observation

OBS-017 · Flagship LLM + MCP vs. notebook-with-tuning — time, token, and cost comparison. Long-term cost concern and pathways to reduce Gen AI execution cost.

**Date:** 2026-06-18
**Source:** Engineer direct comparison from prior project experience
**Related:** OBS-016 (routine pipeline validation), OBS-011 (CNC analogy), DECISION: notebook-to-routine replacement

### The prior approach
The equivalent capability — extracting requirements from a Capella diagram into a structured artifact — was previously built as a Jupyter notebook authored with agent assistance, then tuned to run on less powerful (lower-cost) LLMs. That process took days and consumed a large number of tokens across authoring, debugging, and tuning cycles. Each pass to make the notebook work on a weaker model required re-testing, prompt adjustment, and further iteration — compounding token cost significantly.

### The routine_def approach (EBSD_300 session, 2026-06-18)
The extract_requirements_from_diagram_v1 routine was authored in a single session, validated in 3 cycles, generalised in one update, and executed cleanly twice — two different diagrams, two different phases — within the same session. Total time: hours, not days. No tuning for a different model because the routine runs on the same flagship LLM that authored it.

### The engineer's economic assessment
Running a flagship LLM end-to-end (authoring + execution) is personally less costly in both time and money than the multi-day notebook authoring + multi-pass weaker-model tuning cycle. The productivity of the flagship model at authoring time eliminates tuning overhead entirely. Net cost is lower even though per-token rate is higher.

### The long-term cost concern
The engineer identified a legitimate concern: routine execution cost at scale. A routine executed frequently — on every commit, across many diagrams, in a CSID pipeline — accumulates token cost. One extraction run is cheap. The same routine run automatically on 10 diagrams after every push, across 5 projects, is a different cost profile. This concern is real and should be examined architecturally.

### Pathways to reduce long-term Gen AI execution cost

**1. Compiled routines — code generation from routine_def**
Once a routine is validated and stable, generate a deterministic Python/capellambse script from it. The LLM handles authoring and reasoning-intensive steps only; mechanical steps (browse, resolve, fabric, parse, CSV, write, push) run as code at zero token cost. The routine_def becomes the specification; the compiled script is the production executor.

**2. Structured output caching and fabric diffing**
For routines that run on the same diagram repeatedly (CSID pipeline per commit), cache the prior fabric output and diff against the new run. Only re-run LLM analysis on changed sections. Token cost scales with model change rate, not model size. Unchanged content is free.

**3. Tiered execution model — route steps by reasoning requirement**
Split routine steps by reasoning complexity:
- Mechanical steps (browse, resolve, fabric, parse, write, push) → compiled code, zero tokens
- Light reasoning (data quality flagging, typo detection, duplicate check) → smaller cheaper model
- Deep reasoning (impact analysis, FMEA, gap identification, requirement drafting) → flagship LLM only when needed
The routine_def step structure already supports this — each step could carry a model_tier tag that the executor uses to route.

**4. Batch execution scheduling**
Run low-urgency routines (baseline extraction, traceability reports) on a schedule (nightly, weekly) rather than per-commit. Only blocking integrity checks run per-commit. Reduces execution frequency without reducing coverage.

**5. Prompt compression for mature routines**
As a routine stabilises, compress the prompt_template — remove exploratory language, tighten step descriptions, eliminate redundancy. A mature routine prompt can be significantly shorter than its initial authoring version without losing execution quality. Fewer input tokens per run.

**6. Fine-tuned smaller model for mature routine classes**
Once a class of routines (e.g. requirements extraction) has been executed many times on flagship LLM with high-quality outputs, those input/output pairs become fine-tuning data for a smaller model. A fine-tuned 8B–13B model running locally could execute mature extraction routines at near-zero marginal cost. Flagship LLM remains the authoring and reasoning layer; fine-tuned model handles the pattern-execution layer.

### The strategic framing
The concern is real but the solution is architectural, not a reason to avoid routines. The right pattern is:
- Author on flagship — fast, low total cost, high quality output
- Execute mechanically where possible — compiled code for deterministic steps
- Reserve flagship for reasoning — only where it adds value code cannot replicate
- Reduce execution frequency — batch where urgency permits
- Fine-tune for maturity — as routines stabilise, migrate execution to cheaper models

The routine_def format is implementation-agnostic. Today it drives a flagship LLM. Tomorrow it could drive a compiled script, a smaller model, or a hybrid. The contract (variables, steps, outputs) stays the same; the executor changes.

### Connection to CNC analogy (OBS-011)
Same cost trajectory as CNC machining: initial programming on expensive CAD/CAM software, execution on cheap commodity hardware. The intelligence is in the program, not the machine. The routine_def is the CNC program. Compiled execution is the commodity machine. Fine-tuning is the dedicated production cell.

### For the paper
> *The flagship LLM is the right tool for authoring routines — its speed and reasoning quality eliminate the multi-day tuning cycles that characterised the notebook approach. But production execution of stable routines does not require flagship reasoning. The routine_def format enables a cost migration path: author on flagship, compile the mechanical steps to code, reserve LLM execution for the reasoning steps that code cannot replicate, and fine-tune a smaller model as each routine class matures. The intelligence stays in the routine definition. The execution cost approaches zero as the routine ages.*

**References:** `434be3f3-e826-41cf-af6a-31875f5b6aed`

---

## 2026-06-18T13:39:23Z — observation

OBS-018 · The artifact repository is the bigger story — fabric is the data layer, the artifact repo is the knowledge layer.

**Date:** 2026-06-18
**Source:** Engineer insight, end of EBSD_300 requirements extraction session

### The insight
The artifact repository — and how the KP is using it — is becoming a more significant contribution than the fabric capability. The engineer identified this explicitly after observing the viewer presenting a dashboard of artifacts produced across a single session.

### Why this matters for framing the paper

The capella-fabric capability is genuinely novel and technically impressive. Semantic compression of a complex MBSE metamodel into LLM-readable YAML, scoped to a diagram or chain, with full relationship resolution — that is real engineering work and a real technical contribution. It is the right answer to "how do you make a Capella model accessible to an LLM."

But fabric is an input mechanism. It answers: how does the LLM read the model?

The artifact repository answers a different and arguably more important question: where does the knowledge go after the LLM has reasoned over it?

And the answer the KP has demonstrated — across Road Grader and now EBSD_300 — is that the knowledge goes into a structured, versioned, queryable, viewable repository that accumulates across sessions, feeds future reasoning, seeds routines, and presents as a dashboard to the engineer. That is a knowledge management system for systems engineering. It did not exist before this workflow.

### What the artifact repo actually is

It is not a file store. It is not a log. It is a **persistent engineering intelligence layer** that sits between the model and the engineer, accumulating structured knowledge that neither the model nor the engineer would produce alone.

The model stores structure. The engineer carries intent. The artifact repo stores the synthesis — the extracted, interpreted, curated, and persisted output of the reasoning that happens when a capable LLM works with a capable engineer over a capable model.

That synthesis is the thing that has been missing from MBSE practice. Not better modeling tools. Not smarter engineers. The persistent, structured, versioned record of what the model means — maintained continuously as the model evolves.

### The shift in what the paper should argue

The original paper thesis was approximately: "AI-assisted MBSE via fabric generation enables faster, better model authoring."

The stronger thesis, supported by what has actually emerged across both projects, is:

> *The real contribution of AI-assisted MBSE is not faster model authoring — it is the creation of a persistent engineering knowledge layer that did not previously exist. The artifact repository is that layer. Fabric generation is the mechanism that makes model content available to it. Routine_defs are the repeatable processes that fill it. The viewer is the interface through which it becomes actionable. Together they constitute a knowledge management system for systems engineering — one that accumulates value with every session, every commit, and every routine execution.*

### What this means for capability priority

If the artifact repo is the bigger story, then the investments that make it more valuable should be prioritised:

- **Viewer capability** — making artifacts readable, browsable, and shareable is the interface layer of the knowledge system. Every improvement here multiplies the value of every artifact.
- **Routine library** — routines are the automated fill mechanism. More routines means the knowledge base grows faster and more consistently.
- **Cross-artifact reasoning** — the next frontier: routines that reason over multiple artifacts simultaneously (e.g. compare [LAB] Requirements against [SAB] Context with Needs to identify gaps, or cross-reference FMEA against requirements coverage). This is only possible because the artifacts are structured and co-located.
- **Artifact schema evolution** — as the types of knowledge being captured mature (routine_def, prompt_def, FMEA, RTM, decision, observation), the schema should evolve to support richer querying and linking between artifact types.

Fabric generation remains essential — it is the read interface to the model. But it is infrastructure. The artifact repo is the product.

### The Deming connection restated

Deming's system of profound knowledge requires knowledge to be captured, structured, and built upon. The artifact repo is where that happens in this workflow. The model is the system. The fabric is the measurement instrument. The artifact repo is the accumulated knowledge of how the system behaves, what decisions have been made about it, what its risks are, and what it needs to become. That is profound knowledge in Deming's sense — and it is what has been missing from MBSE practice until now.

### For the paper title and abstract

Consider reframing from a fabric-first framing to a knowledge-layer framing:

Current implied framing: "We built a tool that lets LLMs read Capella models."

Stronger framing: "We built the missing knowledge layer for model-based systems engineering — a persistent, structured, versioned repository of engineering intelligence that accumulates across sessions, feeds automated pipelines, and presents as a living dashboard to the engineer. Fabric generation and AI reasoning are the mechanisms. The knowledge layer is the contribution."

The fabric capability is a section of the paper. The knowledge layer is the thesis.
