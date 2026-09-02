"""Ways of showing a MitID login to the person doing it.

The protocol in mitid.core reports everything through callbacks and draws
nothing itself, because a QR frame belongs on a terminal in one program and in
a Textual widget in the next. These are the two renderings worth sharing:

    mitid.ui.console  status lines, a scannable QR and a code box, on stderr
    mitid.ui.tui      the same login as a Textual screen (needs the `textual`
                      extra; `pip install mitid-client[textual]`)
"""
