import sqlite3
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.io as pio
from flask import Flask, request, render_template_string

app = Flask(__name__)
DB = "sales.db"
REQUIRED = {"order_id", "order_date", "product", "quantity", "unit_price"}

PAGE = """
<!doctype html>
<html>
<head>
  <title>Sales Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body{font:15px Arial;background:#f3f5fa;color:#172033;margin:0}
    main{max-width:1100px;margin:35px auto;padding:0 18px}
    h1{margin-bottom:5px}.muted{color:#68758b}
    form,.card{background:white;padding:18px;border-radius:12px;margin:16px 0}
    button{background:#526fff;color:white;border:0;padding:10px 15px;border-radius:7px}
    .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
    .metric{background:white;padding:18px;border-radius:12px}
    .metric b{display:block;font-size:23px;margin-top:12px}
    .charts{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .error{color:#b42318}.success{color:#087443}
    table{width:100%;border-collapse:collapse;background:white}
    td,th{text-align:left;padding:10px;border-bottom:1px solid #e6eaf0}
    @media(max-width:700px){.metrics{grid-template-columns:1fr 1fr}.charts{grid-template-columns:1fr}}
  </style>
</head>
<body><main>
  <h1>Sales Dashboard</h1><p class="muted">Upload and analyze your sales data</p>
  <form method="post" enctype="multipart/form-data">
    <input type="file" name="file" accept=".csv" required>
    <button type="submit">Upload CSV</button>
    <p class="{{ message_type }}">{{ message }}</p>
  </form>
  <section class="metrics">
    <div class="metric">Total revenue<b>₹{{ "%.2f"|format(revenue) }}</b></div>
    <div class="metric">Total orders<b>{{ orders }}</b></div>
    <div class="metric">Average order value<b>₹{{ "%.2f"|format(aov) }}</b></div>
    <div class="metric">Month-over-month<b>{{ growth }}</b></div>
  </section>
  <section class="charts">
    <div class="card">{{ monthly_chart|safe }}</div>
    <div class="card">{{ product_chart|safe }}</div>
  </section>
  <div class="card"><h3>Recent sales</h3>{{ table|safe }}</div>
</main></body></html>
"""


def read_sales():
    with sqlite3.connect(DB) as conn:
        try:
            return pd.read_sql_query("SELECT * FROM sales", conn)
        except Exception:
            return pd.DataFrame()


@app.route("/", methods=["GET", "POST"])
def dashboard():
    message = ""
    message_type = ""

    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            message = "Please choose a CSV file."
            message_type = "error"
        elif not file.filename.lower().endswith(".csv"):
            message = "Invalid file type. Please upload a CSV."
            message_type = "error"
        else:
            try:
                df = pd.read_csv(BytesIO(file.read()))
                df.columns = df.columns.str.strip().str.lower()
                missing = REQUIRED - set(df.columns)

                if df.empty:
                    raise ValueError("The CSV has no data rows.")
                if missing:
                    raise ValueError("Missing columns: " + ", ".join(sorted(missing)))

                df = df[list(REQUIRED)].drop_duplicates().copy()
                df["order_id"] = df["order_id"].astype("string").str.strip()
                df["product"] = df["product"].astype("string").str.strip()
                df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
                df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
                df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")

                valid = (
                    df["order_id"].notna() & df["order_id"].ne("") &
                    df["product"].notna() & df["product"].ne("") &
                    df["order_date"].notna() & df["quantity"].gt(0) &
                    df["unit_price"].notna() & df["unit_price"].ge(0)
                )
                df = df.loc[valid].copy()
                if df.empty:
                    raise ValueError("No valid sales rows found.")

                df["revenue"] = df["quantity"] * df["unit_price"]
                df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%d")
                with sqlite3.connect(DB) as conn:
                    df.to_sql("sales", conn, if_exists="replace", index=False)

                message = f"Imported {len(df)} valid rows. Duplicates and invalid rows were removed."
                message_type = "success"
            except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
                message = str(error)
                message_type = "error"

    df = read_sales()
    revenue = float(df["revenue"].sum()) if not df.empty else 0
    orders = int(df["order_id"].nunique()) if not df.empty else 0
    aov = revenue / orders if orders else 0
    growth = "—"
    monthly_chart = "<p>Upload a CSV to see sales trends.</p>"
    product_chart = "<p>Upload a CSV to see top products.</p>"
    table = "<p>No sales data yet.</p>"

    if not df.empty:
        df["order_date"] = pd.to_datetime(df["order_date"])
        monthly = df.groupby(df["order_date"].dt.to_period("M"))["revenue"].sum().sort_index()
        if len(monthly) >= 2 and monthly.iloc[-2] != 0:
            change = (monthly.iloc[-1] - monthly.iloc[-2]) / monthly.iloc[-2] * 100
            growth = f"{change:+.1f}%"

        month_df = monthly.rename_axis("Month").reset_index(name="Revenue")
        month_df["Month"] = month_df["Month"].astype(str)
        fig = px.line(month_df, x="Month", y="Revenue", markers=True, title="Monthly Revenue")
        monthly_chart = pio.to_html(fig, full_html=False, include_plotlyjs=False)

        top = df.groupby("product", as_index=False)["revenue"].sum()
        top = top.nlargest(5, "revenue")
        fig = px.bar(top, x="revenue", y="product", orientation="h",
                     title="Top 5 Products by Revenue")
        product_chart = pio.to_html(fig, full_html=False, include_plotlyjs=False)

        recent = df.sort_values("order_date", ascending=False).head(8)
        table = recent.to_html(index=False, columns=[
            "order_id", "order_date", "product", "quantity", "unit_price", "revenue"
        ], border=0)

    return render_template_string(
        PAGE, message=message, message_type=message_type,
        revenue=revenue, orders=orders, aov=aov, growth=growth,
        monthly_chart=monthly_chart, product_chart=product_chart, table=table
    )


if __name__ == "__main__":
    app.run(debug=True)