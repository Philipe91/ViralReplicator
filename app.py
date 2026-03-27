from flask import Flask, render_template, jsonify
from flask_cors import CORS
import pandas as pd
import os
import threading
from main import run_pipeline

app = Flask(__name__)
CORS(app)

CSV_FILE = "virais_detectados.csv"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    if not os.path.exists(CSV_FILE):
        return jsonify({"data": [], "status": "no_data"})
    
    try:
        df = pd.read_csv(CSV_FILE)
        # Drop nan values or replace with empty string
        df = df.fillna('')
        
        # Sort by viral_score descending se a coluna existir
        if 'viral_score' in df.columns:
            df['viral_score'] = pd.to_numeric(df['viral_score'], errors='coerce')
            df = df.sort_values(by='viral_score', ascending=False)
            
        data = df.to_dict(orient="records")
        return jsonify({"data": data, "status": "success"})
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"})

@app.route("/api/run")
def trigger_run():
    # Dispara o radar via Thread pra não travar a request
    thread = threading.Thread(target=run_pipeline)
    thread.daemon = True
    thread.start()
    return jsonify({"message": "Radar operando na gringa em segundo plano!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
