from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_file, abort
from datetime import datetime
import json
import pandas as pd
import hashlib
import secrets
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Change this to a secure key

# Password Security
def generate_salt():
    return secrets.token_hex(16)

def hash_password(password, salt):
    return hashlib.sha256((password + salt).encode()).hexdigest()

# Set your desired password (hashed with salt)
SALT = generate_salt()
HASHED_PASSWORD = hash_password("Sapphire@123", SALT)  # Replace with your desired password

# Database
DB_FILE = "database.json"
COLUMNS = [
    "Sr#", "Machine Type", "Brand", "Model", "Serial Number", "Head Number",
    "Current Location", "Handed Over to", "Accessories", "Previous Location", "TimeStamp"
]

# Load database
def load_database():
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# Save database
def save_database(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Removed IP Filtering completely to allow all network access

# Routes
@app.route("/")
def home():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    database = load_database()
    return render_template("index.html", database=database, columns=COLUMNS, total_entries=len(database))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password")
        if hash_password(password, SALT) == HASHED_PASSWORD:
            session["logged_in"] = True
            session["role"] = "admin"  # Default role
            return redirect(url_for("home"))
        flash("Incorrect password!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/reset_password", methods=["POST"])
def reset_password():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    global SALT, HASHED_PASSWORD

    old_password = request.form.get("old_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if hash_password(old_password, SALT) != HASHED_PASSWORD:
        flash("Incorrect old password!", "error")
    elif new_password != confirm_password:
        flash("Passwords do not match!", "error")
    elif len(new_password) < 8 or not any(char.isdigit() for char in new_password) or not any(char in "!@#$%^&*()" for char in new_password):
        flash("Password must be at least 8 characters long, contain a number, and a special character!", "error")
    else:
        SALT = generate_salt()
        HASHED_PASSWORD = hash_password(new_password, SALT)
        flash("Password reset successfully!", "success")
    return redirect(url_for("home"))

@app.route("/get_machine")
def get_machine():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    headNumber = request.args.get("headNumber", "").lower()
    database = load_database()

    for machine in database:
        if machine["Head Number"].lower() == headNumber:
            return jsonify({"success": True, "machine": machine})

    return jsonify({"success": False, "message": "Machine not found!"})

@app.route("/move_machine", methods=["POST"])
def move_machine():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    headNumber = request.form.get("headNumber")
    newLocation = request.form.get("newLocation")
    handedTo = request.form.get("handedTo")
    accessories = request.form.get("accessories")

    database = load_database()
    for machine in database:
        if machine["Head Number"].lower() == headNumber.lower():
            machine["Previous Location"] = machine["Current Location"]
            machine["Current Location"] = newLocation
            machine["Handed Over to"] = handedTo
            machine["Accessories"] = accessories
            machine["TimeStamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_database(database)
            return jsonify({"success": True, "message": "Machine moved successfully!"})

    return jsonify({"success": False, "message": "Machine not found!"})

@app.route("/add_machine", methods=["POST"])
def add_machine():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    new_machine = {col: request.form.get(col) for col in COLUMNS[1:-1]}  # Exclude TimeStamp
    new_machine["Sr#"] = str(len(load_database()) + 1)
    new_machine["TimeStamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Auto-generate timestamp

    database = load_database()
    database.append(new_machine)
    save_database(database)
    return jsonify({"success": True, "message": "Machine added successfully!"})

@app.route("/remove_machine", methods=["POST"])
def remove_machine():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    headNumber = request.form.get("headNumber")
    database = load_database()
    database = [machine for machine in database if machine["Head Number"] != headNumber]
    save_database(database)
    return jsonify({"success": True, "message": "Machine removed successfully!"})

@app.route("/edit_machine", methods=["POST"])
def edit_machine():
    if not session.get("logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    headNumber = request.form.get("headNumber")
    updates = {col: request.form.get(col) for col in COLUMNS[1:-1]}  # Exclude TimeStamp

    database = load_database()
    for machine in database:
        if machine["Head Number"].lower() == headNumber.lower():
            for key, value in updates.items():
                if value:
                    machine[key] = value
            machine["TimeStamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Update timestamp
            break

    save_database(database)
    return jsonify({"success": True, "message": "Machine edited successfully!"})

@app.route("/export", methods=["POST"])
def export_data():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    database = load_database()
    if not database:
        flash("No data to export!", "error")
        return redirect(url_for("home"))

    try:
        df = pd.DataFrame(database)
        df.to_excel("database_export.xlsx", index=False)
        return send_file("database_export.xlsx", as_attachment=True)
    except Exception as e:
        flash(f"Failed to export: {e}", "error")
        return redirect(url_for("home"))

@app.route("/export_filtered", methods=["POST"])
def export_filtered():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    headNumber = request.form.get("headNumber", "").lower()
    location = request.form.get("location", "").lower()
    serialNumber = request.form.get("serialNumber", "").lower()
    modelNumber = request.form.get("modelNumber", "").lower()

    database = load_database()
    filtered_data = [
        row for row in database
        if (headNumber in row["Head Number"].lower()) and
           (location in row["Current Location"].lower()) and
           (serialNumber in row["Serial Number"].lower()) and
           (modelNumber in row["Model"].lower())
    ]

    if not filtered_data:
        flash("No filtered data to export!", "error")
        return redirect(url_for("home"))

    try:
        df = pd.DataFrame(filtered_data)
        df.to_excel("filtered_data_export.xlsx", index=False)
        return send_file("filtered_data_export.xlsx", as_attachment=True)
    except Exception as e:
        flash(f"Failed to export: {e}", "error")
        return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)