# Non-interactive override for Slicer extension self-tests.
#
# Some extension tests (typically GPU segmentation) pop a modal confirmation --
#   "Selected device (CUDA) is not currently available ... default to CPU device.
#    Running the segmentation may take up to 1 hour. Would you like to proceed?"
# -- and block an unattended run waiting for a human click. Seen in
# DentalSegmentator / AutomatedDentalTools / UpperAirwaySegmentator, which share
# a SegmentationWidget.py that calls qt.QMessageBox.question() with no
# slicer.app.testingEnabled() guard.
#
# The standard sentinel is slicer.app.testingEnabled() (set by --testing); a
# well-behaved module guards its dialog with it. This file is the forest-side
# override for modules that DON'T, and it works at TWO layers because the
# offending calls are raw Qt, not slicer.util:
#
#   1. A QTimer that dismisses any modal dialog Qt shows. This is the robust
#      catch-all: qt.QMessageBox.question() spins a nested event loop, and Qt
#      timers fire inside nested loops, so the dialog is rejected/closed the
#      instant it appears. Catches raw QMessageBox AND slicer.util confirms.
#   2. slicer.util.confirm* patches, for the modules that DO use that path --
#      cheaper and more precise than waiting for the timer tick.
#
# Inject at test startup, e.g.:
#   Slicer --testing --no-splash --python-script bin/slicer-noninteractive-test-override.py \
#          --python-code "<the actual test>"
#
# Answer policy (env-configurable):
#   SLICER_TEST_CONFIRM=decline (default) -> reject/No/Cancel, so a CPU-fallback
#       hour-long job is NOT started; the test skips the heavy path.
#   SLICER_TEST_CONFIRM=accept            -> accept/Yes/Ok (only when you WANT
#       the heavy path, e.g. a machine with a real GPU).
#
# Every auto-answer is logged so a suppressed prompt is never silent.

import os
import qt
import slicer
import slicer.util

_POLICY = os.environ.get("SLICER_TEST_CONFIRM", "decline").strip().lower()
_ACCEPT = _POLICY == "accept"


def _log(source, text, answer):
    msg = (text or "").replace("\n", " ")[:120]
    print(f"[noninteractive-override] {source} auto-answered "
          f"{'ACCEPT' if answer else 'DECLINE'} (policy={_POLICY}): {msg}")


# --- Layer 1: dismiss any modal dialog (catches raw qt.QMessageBox) -----------
def _dismiss_modal():
    w = qt.QApplication.activeModalWidget()
    if w is None:
        return
    title = ""
    try:
        title = w.windowTitle
    except Exception:
        pass
    _log("modal-dialog", title, _ACCEPT)
    # For a QMessageBox, accept() clicks the AcceptRole button (Yes/Ok) and
    # reject() clicks the RejectRole button (No/Cancel) / Escape. Both make the
    # blocking question()/exec() return the corresponding standard button.
    try:
        if _ACCEPT:
            w.accept()
        else:
            w.reject()
    except Exception:
        w.close()


_timer = qt.QTimer()
_timer.setInterval(300)
_timer.connect("timeout()", _dismiss_modal)
_timer.start()


# --- Layer 2: slicer.util.confirm* (precise, for modules that use it) ---------
def _yes_no(text, windowTitle=None, parent=None, **kwargs):
    _log("confirmYesNoDisplay", text, _ACCEPT)
    return _ACCEPT


def _ok_cancel(text, windowTitle=None, parent=None, **kwargs):
    _log("confirmOkCancelDisplay", text, _ACCEPT)
    return _ACCEPT


def _retry_close(text, windowTitle=None, parent=None, **kwargs):
    # Retry would loop forever unattended; always Close (False).
    _log("confirmRetryCloseDisplay", text, False)
    return False


slicer.util.confirmYesNoDisplay = _yes_no
slicer.util.confirmOkCancelDisplay = _ok_cancel
slicer.util.confirmRetryCloseDisplay = _retry_close

print(f"[noninteractive-override] installed; testingEnabled="
      f"{slicer.app.testingEnabled()} policy={_POLICY} (modal-dismiss timer + util patches)")
