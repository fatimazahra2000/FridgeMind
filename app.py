from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
import io

app = Flask(__name__)
CORS(app)
DB = "fridge.db"

# ---------------- INIT DB + SEED ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        qty INTEGER,
        price REAL,
        expiry TEXT,
        barcode TEXT
    )
    """)
    conn.commit()
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        today = datetime.now().date()
        demo = [
            ("Lait demi-ecrémé",     6,  8.50,  str(today + timedelta(days=2)),  "3017620422003"),
            ("Yaourt nature",         4,  4.20,  str(today + timedelta(days=5)),  "3033490004743"),
            ("Poulet entier",         2, 45.00,  str(today + timedelta(days=1)),  "3256220088149"),
            ("Fromage Kiri",          3, 18.90,  str(today - timedelta(days=2)),  "3073781011812"),
            ("Jus d'orange",          2, 12.00,  str(today + timedelta(days=14)), "5449000131805"),
            ("Beurre doux",           1, 22.50,  str(today + timedelta(days=30)), "3017620401039"),
            ("Oeufs frais x12",       1, 19.00,  str(today + timedelta(days=20)), "3560070976478"),
            ("Mortadelle",            2, 14.50,  str(today - timedelta(days=1)),  "3270190113402"),
            ("Creme fraiche",         1, 11.00,  str(today + timedelta(days=6)),  "3245411100038"),
            ("Eau minérale x6",       3,  9.00,  str(today + timedelta(days=90)), "5449000000439"),
        ]
        c.executemany("INSERT INTO products(name,qty,price,expiry,barcode) VALUES(?,?,?,?,?)", demo)
        conn.commit()
    conn.close()

init_db()

# ---------------- HELPERS ----------------
def get_all_products():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM products ORDER BY expiry ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def compute_kpis(rows):
    today = datetime.now().date()
    total = len(rows)
    expired = near = 0
    waste = total_value = 0.0
    categories = {}
    ok_count = 0

    for r in rows:
        try:
            expiry = datetime.strptime(r[4], "%Y-%m-%d").date()
        except:
            continue
        qty   = r[2] or 0
        price = r[3] or 0.0
        val   = qty * price
        total_value += val
        days  = (expiry - today).days

        if days < 0:
            expired += 1
            waste   += val
        elif days <= 7:
            near += 1
        else:
            ok_count += 1

        cat = (r[1] or "Autre").split()[0]
        categories[cat] = categories.get(cat, 0) + val

    top = sorted(categories.items(), key=lambda x: -x[1])[:6]
    return {
        "total": total, "expired": expired, "near": near,
        "ok": ok_count,
        "waste": round(waste, 2),
        "total_value": round(total_value, 2),
        "chart_labels": [x[0] for x in top],
        "chart_values": [round(x[1], 2) for x in top],
    }

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/products", methods=["GET"])
def get_products():
    rows = get_all_products()
    return jsonify([{"id":r[0],"name":r[1],"qty":r[2],"price":r[3],"expiry":r[4],"barcode":r[5]} for r in rows])

@app.route("/api/products", methods=["POST"])
def add_product():
    d = request.json
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO products(name,qty,price,expiry,barcode) VALUES(?,?,?,?,?)",
        (d["name"], d["qty"], d["price"], d["expiry"], d.get("barcode","")))
    conn.commit(); conn.close()
    return jsonify({"message": "added"})

@app.route("/api/products/<int:id>", methods=["PUT"])
def update_product(id):
    d = request.json
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE products SET name=?,qty=?,price=?,expiry=?,barcode=? WHERE id=?",
        (d["name"], d["qty"], d["price"], d["expiry"], d.get("barcode",""), id))
    conn.commit(); conn.close()
    return jsonify({"message": "updated"})

@app.route("/api/products/<int:id>", methods=["DELETE"])
def delete_product(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM products WHERE id=?", (id,))
    conn.commit(); conn.close()
    return jsonify({"message": "deleted"})

@app.route("/api/scan", methods=["POST"])
def scan_barcode():
    barcode = request.json.get("barcode","")
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE barcode=?", (barcode,))
    r = c.fetchone(); conn.close()
    if r:
        return jsonify({"found":True,"product":{"id":r[0],"name":r[1],"qty":r[2],"price":r[3],"expiry":r[4],"barcode":r[5]}})
    return jsonify({"found":False,"barcode":barcode})

@app.route("/api/kpis")
def kpis():
    return jsonify(compute_kpis(get_all_products()))

# ---------------- EXPORT PDF ----------------
@app.route("/api/export/pdf")
def export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)
    from reportlab.lib.units import cm
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.graphics import renderPDF

    rows  = get_all_products()
    kpis  = compute_kpis(rows)
    today = datetime.now().date()

    # ── palette ─────────────────────────────────────
    NAVY    = colors.HexColor("#0F172A")
    BLUE    = colors.HexColor("#3B82F6")
    BLUE_LT = colors.HexColor("#DBEAFE")
    BORDER  = colors.HexColor("#CBD5E1")
    ROW_A   = colors.HexColor("#F8FAFC")
    RED_BG  = colors.HexColor("#FEE2E2")
    RED_C   = colors.HexColor("#DC2626")
    AMB_BG  = colors.HexColor("#FEF9C3")
    AMB_C   = colors.HexColor("#D97706")
    GRN_BG  = colors.HexColor("#D1FAE5")
    GRN_C   = colors.HexColor("#059669")
    SLATE   = colors.HexColor("#475569")
    LIGHT   = colors.HexColor("#94A3B8")
    WHITE   = colors.white

    W = A4[0] - 3.6*cm   # usable width

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm,  bottomMargin=1.5*cm)

    def ps(name="", **kw):
        return ParagraphStyle(name or "x", **kw)

    story = []

    # ════════════════════════════════════════════════
    # 1. HEADER BANNER
    # ════════════════════════════════════════════════
    hdr = Table([[
        Paragraph(
            '<font name="Helvetica-Bold" size="20" color="#FFFFFF">FridgeMind</font><br/>'
            '<font name="Helvetica" size="9" color="#93C5FD">Rapport de stock — inventaire complet</font>',
            ps(leading=24)),
        Paragraph(
            f'<font name="Helvetica" size="8" color="#93C5FD">Date du rapport</font><br/>'
            f'<font name="Helvetica-Bold" size="11" color="#FFFFFF">'
            f'{datetime.now().strftime("%d %B %Y")}</font><br/>'
            f'<font name="Helvetica" size="8" color="#93C5FD">'
            f'{datetime.now().strftime("%H:%M")}</font>',
            ps(alignment=2, leading=15))
    ]], colWidths=[W*0.62, W*0.38])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 16),
        ("BOTTOMPADDING", (0,0), (-1,-1), 16),
        ("LEFTPADDING",   (0,0), (0,0),   18),
        ("RIGHTPADDING",  (1,0), (1,0),   18),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [hdr, Spacer(1, 0.45*cm)]

    # ════════════════════════════════════════════════
    # 2. KPI CARDS — vraies données du dashboard
    # ════════════════════════════════════════════════
    waste_pct = round(kpis["waste"] / kpis["total_value"] * 100, 1) if kpis["total_value"] else 0

    def kpi(label, val, sub, bg, border_c, val_c):
        return Paragraph(
            f'<font name="Helvetica" size="7.5" color="#64748B">{label}</font><br/>'
            f'<font name="Helvetica-Bold" size="19" color="{val_c.hexval()}">{val}</font><br/>'
            f'<font name="Helvetica" size="7.5" color="#94A3B8">{sub}</font>',
            ps(alignment=1, leading=20, backColor=bg,
               borderColor=border_c, borderWidth=0.5,
               borderPadding=(10,8,10,8)))

    cw = W / 4
    kpi_tbl = Table([[
        kpi("Total produits",     kpis["total"],           f"{kpis['ok']} en bonne etat",       BLUE_LT, BLUE,  BLUE),
        kpi("Expires",            kpis["expired"],         f"a retirer du stock",                RED_BG,  RED_C, RED_C),
        kpi("Expirent bientot",   kpis["near"],            "dans les 7 prochains jours",         AMB_BG,  AMB_C, AMB_C),
        kpi("Valeur totale",      f"{kpis['total_value']} DH", f"dont {kpis['waste']} DH perdus ({waste_pct}%)", GRN_BG, GRN_C, GRN_C),
    ]], colWidths=[cw]*4, rowHeights=[1.7*cm])
    kpi_tbl.setStyle(TableStyle([
        ("LINEAFTER",  (0,0),(2,0), 0.5, BORDER),
        ("TOPPADDING", (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("LEFTPADDING",(0,0),(-1,-1), 0),
        ("RIGHTPADDING",(0,0),(-1,-1), 0),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
    ]))
    story += [kpi_tbl, Spacer(1, 0.5*cm)]

    # ════════════════════════════════════════════════
    # 3. BARRE DE STATUT VISUELLE (mini chart inline)
    # ════════════════════════════════════════════════
    if kpis["total"] > 0:
        bar_w = W
        bar_h = 10
        ok_w   = bar_w * (kpis["ok"]      / kpis["total"])
        near_w = bar_w * (kpis["near"]    / kpis["total"])
        exp_w  = bar_w * (kpis["expired"] / kpis["total"])

        d = Drawing(bar_w, bar_h + 20)
        x = 0
        for w, col in [(ok_w, GRN_C), (near_w, AMB_C), (exp_w, RED_C)]:
            if w > 0:
                d.add(Rect(x, 10, w, bar_h, fillColor=col, strokeColor=None))
                x += w
        # légende
        lx = 0
        for label, w, col in [
            (f"OK: {kpis['ok']}", ok_w, GRN_C),
            (f"Bientot: {kpis['near']}", near_w, AMB_C),
            (f"Expires: {kpis['expired']}", exp_w, RED_C),
        ]:
            if w > 0:
                d.add(String(lx + w/2, 2, label,
                    fontSize=7, fillColor=col,
                    textAnchor="middle", fontName="Helvetica-Bold"))
            lx += w

        story += [d, Spacer(1, 0.35*cm)]

    # ════════════════════════════════════════════════
    # 4. TITRE SECTION
    # ════════════════════════════════════════════════
    story.append(Paragraph(
        '<font name="Helvetica-Bold" size="11" color="#0F172A">Detail du stock</font>',
        ps(spaceAfter=4)))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=6))

    # ════════════════════════════════════════════════
    # 5. TABLEAU PRODUITS
    # ════════════════════════════════════════════════
    def hcell(txt):
        return Paragraph(f'<font name="Helvetica-Bold" size="8.5" color="#FFFFFF">{txt}</font>',
                         ps(alignment=1))

    headers = [hcell("Produit"), hcell("Qte"), hcell("Prix unit."),
               hcell("Valeur"), hcell("Expiration"), hcell("Jours"), hcell("Statut")]

    col_w = [W*0.27, W*0.07, W*0.11, W*0.11, W*0.13, W*0.09, W*0.22]
    tdata = [headers]
    extra_styles = []

    for i, r in enumerate(rows, 1):
        try:
            expiry = datetime.strptime(r[4], "%Y-%m-%d").date()
            days   = (expiry - today).days
        except:
            days = 999

        qty   = r[2] or 0
        price = r[3] or 0.0
        val   = qty * price

        if days < 0:
            status_txt = "EXPIRE"
            status_col = RED_C
            days_txt   = f"{abs(days)}j dep."
            extra_styles += [("BACKGROUND",(0,i),(-1,i), colors.HexColor("#FFF5F5"))]
            row_bg = colors.HexColor("#FFF5F5")
        elif days <= 7:
            status_txt = f"Bientot"
            status_col = AMB_C
            days_txt   = f"{days}j rest."
            extra_styles += [("BACKGROUND",(0,i),(-1,i), colors.HexColor("#FFFBEB"))]
            row_bg = colors.HexColor("#FFFBEB")
        else:
            status_txt = "OK"
            status_col = GRN_C
            days_txt   = f"{days}j"
            row_bg = ROW_A if i % 2 == 0 else WHITE

        name_p = Paragraph(
            f'<font name="Helvetica-Bold" size="8.5" color="#1E293B">{r[1]}</font>',
            ps(leading=11))
        status_p = Paragraph(
            f'<font name="Helvetica-Bold" size="8" color="{status_col.hexval()}">{status_txt}</font>',
            ps(alignment=1))

        def c(txt, bold=False, align=1, col="#334155"):
            fn = "Helvetica-Bold" if bold else "Helvetica"
            return Paragraph(f'<font name="{fn}" size="8.5" color="{col}">{txt}</font>',
                             ps(alignment=align))

        tdata.append([
            name_p,
            c(str(qty), align=1),
            c(f"{price:.2f}", align=1),
            c(f"{val:.2f}", bold=True, col="#0F172A", align=1),
            c(r[4], align=1),
            c(days_txt, align=1),
            status_p,
        ])

    base = [
        ("BACKGROUND",    (0,0), (-1,0),  BLUE),
        ("LINEBELOW",     (0,0), (-1,0),  1.2, NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [ROW_A, WHITE]),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ] + extra_styles

    prod_tbl = Table(tdata, colWidths=col_w, repeatRows=1)
    prod_tbl.setStyle(TableStyle(base))
    story += [prod_tbl, Spacer(1, 0.5*cm)]

    # ════════════════════════════════════════════════
    # 6. RÉSUMÉ FINANCIER
    # ════════════════════════════════════════════════
    story.append(Paragraph(
        '<font name="Helvetica-Bold" size="11" color="#0F172A">Resume financier</font>',
        ps(spaceAfter=4)))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=6))

    fin_data = [
        [Paragraph('<font name="Helvetica-Bold" size="8.5" color="#FFFFFF">Indicateur</font>', ps(alignment=0)),
         Paragraph('<font name="Helvetica-Bold" size="8.5" color="#FFFFFF">Valeur</font>', ps(alignment=2))],
        ["Valeur totale du stock",          f"{kpis['total_value']} DH"],
        ["Pertes (produits expires)",        f"{kpis['waste']} DH"],
        ["Taux de gaspillage",               f"{waste_pct} %"],
        ["Produits sains (non expires)",     f"{kpis['ok'] + kpis['near']} / {kpis['total']}"],
        ["Produits critiques (≤7j + exp.)", f"{kpis['near'] + kpis['expired']} produits"],
    ]
    def fin_row(label, val, i):
        bg = ROW_A if i % 2 == 0 else WHITE
        return [
            Paragraph(f'<font name="Helvetica" size="9" color="#334155">{label}</font>', ps()),
            Paragraph(f'<font name="Helvetica-Bold" size="9" color="#0F172A">{val}</font>', ps(alignment=2)),
        ]
    fin_rows = [fin_data[0]] + [fin_row(fin_data[i][0], fin_data[i][1], i) for i in range(1, len(fin_data))]
    fin_tbl = Table(fin_rows, colWidths=[W*0.70, W*0.30])
    fin_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [ROW_A, WHITE]),
        ("BOX",           (0,0), (-1,-1), 0.5, BORDER),
        ("GRID",          (0,0), (-1,-1), 0.25, BORDER),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story += [fin_tbl, Spacer(1, 0.4*cm)]

    # ════════════════════════════════════════════════
    # 7. FOOTER
    # ════════════════════════════════════════════════
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 0.12*cm))
    story.append(Paragraph(
        f'<font name="Helvetica" size="7.5" color="#94A3B8">'
        f'FridgeMind · Rapport genere le {datetime.now().strftime("%d/%m/%Y a %H:%M")} · '
        f'{kpis["total"]} produit(s) · Valeur : {kpis["total_value"]} DH · '
        f'Pertes : {kpis["waste"]} DH ({waste_pct}%)</font>',
        ps(alignment=1)))

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=True, download_name='fridgemind_report.pdf')

if __name__ == "__main__":
    app.run(debug=True)
