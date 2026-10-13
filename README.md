# Sales Dashboard

A Flask dashboard that analyzes sales CSV files using Pandas and Plotly, and stores cleaned sales data in SQLite.

## Run
Install Python packages:
`pip install flask pandas numpy plotly`

Start the app:
`python app.py`

Open `http://127.0.0.1:5000`.

## CSV columns
`order_id, order_date, product, quantity, unit_price`

The dashboard cleans duplicate and invalid rows, then displays revenue, orders, average order value, monthly growth, and top products.