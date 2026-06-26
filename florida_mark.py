import os
import pandas as pd
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
from datetime import datetime

# ── CONFIGURATION ───────────────────────────────────────
IMAGE_FOLDER = "temp_screens3"  # Final batch folder
OUTPUT_FILE = f"vetted_leads_phase3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# ── COLORS ──────────────────────────────────────────────
BG_DARK, BG_CANVAS, TXT_CYAN = "#1e1e1e", "#2d2d2d", "#00ffff"
BTN_KEEP, BTN_SKIP, BTN_REDO = "#5cb85c", "#d9534f", "#f0ad4e"

class FinalPhaseAuditor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Final Phase: Speed Reviewer (2000-3500)")
        self.root.state('zoomed') 
        self.root.configure(bg=BG_DARK)

        if not os.path.exists(IMAGE_FOLDER):
            messagebox.showerror("Error", f"Folder '{IMAGE_FOLDER}' not found!")
            self.root.destroy()
            return

        self.image_files = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        self.index = 0
        self.results = []
        self.lead_count = 0

        if not self.image_files:
            messagebox.showinfo("Empty", f"No images found in {IMAGE_FOLDER}.")
            self.root.destroy()
            return

        self.setup_ui()
        self.load_image()

    def setup_ui(self):
        self.root.columnconfigure(0, weight=4)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # --- LEFT: IMAGE VIEW ---
        left_frame = tk.Frame(self.root, bg=BG_DARK)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.header = tk.Label(left_frame, text="", font=("Arial", 14, "bold"), bg=BG_DARK, fg=TXT_CYAN)
        self.header.pack(pady=5)

        self.canvas = tk.Canvas(left_frame, bg=BG_CANVAS, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # --- RIGHT: SIDEBAR ---
        right_frame = tk.Frame(self.root, bg=BG_DARK, width=300)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=30, pady=60)

        tk.Label(right_frame, text="THE HOME STRETCH", font=("Arial", 14, "bold"), bg=BG_DARK, fg="white").pack(pady=10)
        
        self.stats_label = tk.Label(right_frame, text="Leads Found: 0", font=("Arial", 12), bg=BG_DARK, fg=BTN_KEEP)
        self.stats_label.pack(pady=5)

        btn_opts = {"font": ("Arial", 11, "bold"), "width": 22, "height": 3, "fg": "white"}

        tk.Button(right_frame, text="[1] QUALIFIED LEAD", bg=BTN_KEEP, command=self.mark_lead, **btn_opts).pack(pady=10)
        tk.Button(right_frame, text="[SPACE] DISCARD", bg=BTN_SKIP, command=self.mark_not_lead, **btn_opts).pack(pady=10)
        tk.Button(right_frame, text="[3] RECHECK", bg=BTN_REDO, command=self.mark_recheck, **btn_opts).pack(pady=10)
        
        tk.Label(right_frame, text="────────────────", bg=BG_DARK, fg="gray40").pack(pady=20)
        
        tk.Button(right_frame, text="BACK (B)", bg="#5bc0de", command=self.go_back, **btn_opts).pack(pady=5)
        tk.Button(right_frame, text="FINISH & SAVE", bg="gray30", command=self.save_and_exit, **btn_opts).pack(pady=20)

        # Mappings
        self.root.bind('1', lambda e: self.mark_lead())
        self.root.bind('<space>', lambda e: self.mark_not_lead())
        self.root.bind('3', lambda e: self.mark_recheck())
        self.root.bind('b', lambda e: self.go_back())

    def load_image(self):
        if self.index >= len(self.image_files):
            self.save_and_exit()
            return

        filename = self.image_files[self.index]
        self.header.config(text=f"Total Progress: {self.index + 1} / {len(self.image_files)}")
        
        path = os.path.join(IMAGE_FOLDER, filename)
        self.root.update()
        canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        
        try:
            img = Image.open(path)
            img.thumbnail((canvas_w, canvas_h))
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(canvas_w/2, canvas_h/2, image=self.photo)
        except:
            self.canvas.delete("all")
            self.canvas.create_text(canvas_w/2, canvas_h/2, text="Image Error", fill="white")

    def record_decision(self, status):
        if status == "LEAD": self.lead_count += 1
        self.stats_label.config(text=f"Leads Found: {self.lead_count}")

        filename = self.image_files[self.index]
        self.results.append({
            "filename": filename,
            "decision": status,
            "website": filename.replace('.png', '').replace('_', '.')
        })
        self.index += 1
        self.load_image()

    def go_back(self):
        if self.index > 0:
            self.index -= 1
            if self.results:
                last_decision = self.results.pop()
                if last_decision['decision'] == "LEAD":
                    self.lead_count -= 1
                    self.stats_label.config(text=f"Leads Found: {self.lead_count}")
            self.load_image()

    def mark_not_lead(self): self.record_decision("REJECTED")
    def mark_recheck(self): self.record_decision("RECHECK")
    def mark_lead(self): self.record_decision("LEAD")

    def save_and_exit(self):
        if self.results:
            pd.DataFrame(self.results).to_csv(OUTPUT_FILE, index=False)
            messagebox.showinfo("Saved", f"Final Phase Complete! Exported {self.lead_count} leads.")
        self.root.destroy()

if __name__ == "__main__":
    app = FinalPhaseAuditor()
    app.root.mainloop()