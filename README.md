# KRA Survey Indices Dashboard

Final Streamlit package with corrected top banner spacing, KRA logo as PNG, red/black theme, corporate and departmental survey filters, construct performance, trends, segment analysis, and mapped Excel input.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files

- `app.py` - main Streamlit dashboard
- `dashboard_utils.py` - charts, formatting, CSS, and data utilities
- `survey_indices_entry_sheet_mapped.xlsx` - mapped survey entry workbook
- `assets/kra_logo.png` - PNG logo used in the header
- `requirements.txt` - Python dependencies

## Input workbook sheets

- `Survey_Master`
- `Construct_Master`
- `Corporate_Data`
- `Departmental_Data`
- `Segment_Data`
- `Score_Type_Rules`

## v7 fix
- Fixed Segment Analysis `Segment_Name` KeyError by keeping table data separate from chart data.
- Added safer unique Plotly keys for segment charts.


## v8 update
- Removed the header "Data as at" date box.
- Kept the red/black top accent and improved header balance.
