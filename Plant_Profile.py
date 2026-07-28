# SUPERSEDED — not used by the running app.
#
# Streamlit only auto-discovers pages directly inside pages/ (one level;
# see https://docs.streamlit.io/develop/concepts/multipage-apps).
# This root-level copy of "Plant_Profile.py" was never in that pages/
# directory, so Streamlit has never executed it -- the app's actual
# "Plant Profile" page has always been pages/Plant_Profile.py.
#
# This file previously held a duplicate, independently-edited copy of
# the same page (including a regulatory-evidence rework and an
# evidence-freshness section) that silently diverged from
# pages/Plant_Profile.py, which still had older content. That
# divergence meant the real, user-facing page was missing both
# features even though tests for them existed elsewhere in the repo
# and appeared to pass against this file's content instead.
#
# Fix: pages/Plant_Profile.py now contains the complete, current page
# (this file's former content). This file is kept only as an
# intentionally inert placeholder, pending an explicit decision to
# remove it outright, rather than being silently deleted.
#
# Do not add imports or logic here. Any future Plant Profile change
# belongs in pages/Plant_Profile.py only.
