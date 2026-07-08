# KRA Survey Indices Dashboard

Streamlit dashboard for Corporate and Departmental survey indices for the Tax Research & Analysis Department, Research & Surveys Section.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Main files

- `app.py` - main Streamlit application
- `dashboard_utils.py` - charting, styling, scoring and data utilities
- `survey_indices_entry_sheet_mapped.xlsx` - mapped survey input workbook
- `assets/kra_logo.png` - offline fallback logo asset

The header now uses the official KRA logo link and falls back to the local PNG only if the online logo cannot load.
