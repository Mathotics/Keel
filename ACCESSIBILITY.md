# Accessibility statement

This statement says how Keel is built for people who use a keyboard, a screen reader, or a phone, and how to report a barrier.

Keel is a self-hosted issue tracker. The same product is the web app and the Android app in `mobile/`. Keel is proprietary. Permission to copy or modify it comes from the copyright holder, as [LICENSE](LICENSE) says.

This statement was written on 14 November 2026. It will be updated when the product changes in a way that affects access.

## What we aim for

Every action in the web app should be usable without a mouse and without JavaScript. The Android app should expose its controls to the platform's assistive technology.

Keel has not had a formal accessibility audit. This statement does not claim a conformance level.

## How the web app is built

- Pages are HTML in English, with `lang="en"` on the document.
- Each page has a header, a main region, and a footer.
- Forms have labels. A label is visually hidden when the text around the field already names it, so a screen reader still gets the name.
- Errors are marked as alerts. Notices are marked as status.
- Find is a search form. The home link, the notifications link, and the section navigation have names.
- Moving an issue on the board has a form. Dragging a card is an extra on top of that form. The form remains when JavaScript does not run.
- The same pages reflow for a phone-width browser. Home and Find stay on the bar. The rest of the bar opens from a Menu control.
- The Gantt view includes the issue key and title as text, not only as a bar.

## How the Android app is built

The Android app marks buttons and other controls with a role, and names controls whose visible text is not enough. It has not been audited with a screen reader as a release check.

## Known limits

- There is no published conformance claim, and no assistive-technology pass is required before a release.
- Dragging a card on the board is a pointer action. The accessible path is the Move form.
- On a phone, wide tables scroll sideways. Their columns stay in one row.
- Color distinguishes issue types. The type is also written as text on the issue.

## Reporting a barrier

Report a barrier as a bug through [GitHub issues](https://github.com/Mathotics/Keel/issues/new/choose). A barrier in the product is not a security report. Use the [security policy](SECURITY.md) only when the problem is a security flaw.

Include:

- The page or screen, and what you were trying to do
- The browser or the Android version, and the assistive technology if you used one
- What happened, and what you expected

The copyright holder treats the report as a defect.
