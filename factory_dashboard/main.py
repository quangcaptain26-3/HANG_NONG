import sys
import os
import re
import math
import pandas as pd
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QPushButton, QFileDialog, 
                             QLabel, QFrame, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ==========================================
# 1. CẤU HÌNH CỨNG
# ==========================================
SYSTEM_IP = "10.177.117.1"
SYSTEM_PORT = "8000"

STATIONS = [
    {"name": "PATH", "down": "1033, 1030, 1027", "up": "263, 1052"},
    {"name": "R650", "down": "1205", "up": "1200"},
    {"name": "R770", "down": "1063", "up": "1065"},
    {"name": "R370", "down": "175", "up": "1061"},
    {"name": "ICX-8100", "down": "1039", "up": "1041"},
    {"name": "UX7", "down": "1037", "up": "1067"},
    {"name": "4C", "down": "991", "up": "989"},
    {"name": "4D-Revlon1-3", "down": "987", "up": "798"},
    {"name": "4E-Revlon2-4", "down": "805", "up": "802"},
    {"name": "4J", "down": "972", "up": "971"},
    {"name": "4K", "down": "970", "up": "969"},
    {"name": "4L", "down": "1263", "up": "1260"},
    {"name": "4M", "down": "1257", "up": "1254"},
    {"name": "4N", "down": "1251", "up": "1248"},
    {"name": "4P", "down": "1245", "up": "1242"},
    {"name": "4A-LP48-NEW", "down": "1751", "up": "1749"},
    {"name": "4B-LP8-NEW", "down": "1747", "up": "1744"},
    {"name": "4C-NEW", "down": "1723", "up": "1724"},
    {"name": "4D-Revlon1-3-NEW", "down": "1725", "up": "1726"},
    {"name": "4E-Revlon2-4-NEW", "down": "1727", "up": "1728"}
]

POINT_MAP = {}
for st in STATIONS:
    for p in st['down'].split(','): POINT_MAP[p.strip()] = st['name']
    for p in st['up'].split(','): POINT_MAP[p.strip()] = st['name']

# ==========================================
# 2. THREAD XỬ LÝ DỮ LIỆU
# ==========================================
class DataWorker(QThread):
    oee_data_ready = pyqtSignal(object)
    agv_data_ready = pyqtSignal(dict)
    aoi_data_ready = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.task = ""
        self.file_paths = []

    def run(self):
        if self.task == "OEE": self.process_oee()
        elif self.task == "LOGS": self.process_logs()
        elif self.task == "AOI": self.process_aoi()

    def process_oee(self):
        try:
            df_list = []
            for path in self.file_paths:
                if path.endswith('.csv'): df = pd.read_csv(path)
                else: 
                    try: df = pd.read_excel(path)
                    except:
                        try:
                            dfs = pd.read_html(path, header=0, encoding='utf-8')
                            if dfs: df = dfs[0]
                            else: continue
                        except: continue
                df_list.append(df)
            
            if df_list:
                df = pd.concat(df_list, ignore_index=True)
                df.columns = [str(c).strip() for c in df.columns]
                for col in ['樓層', '綫', '日']:
                    if col in df.columns: df[col] = df[col].astype(str).str.strip()
                if 'OEE' in df.columns:
                    df['OEE_Num'] = df['OEE'].astype(str).str.replace(r'[% ]', '', regex=True).apply(pd.to_numeric, errors='coerce')
                self.oee_data_ready.emit(df)
        except Exception as e: print("Lỗi đọc OEE:", e)

    def process_logs(self):
        try:
            station_counts = {}
            action_counts = {'UP': 0, 'DOWN': 0}
            timeline_counts = {}
            total_tasks = 0
            
            for path in self.file_paths:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                blocks = re.split(r'(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\])', content)
                for i in range(1, len(blocks), 2):
                    time_str = blocks[i]
                    payload = blocks[i+1]
                    
                    if '"points":' in payload:
                        points = re.findall(r'"point":\s*"(\d+)",\s*"action":\s*"(up|down)"', payload)
                        for point, action in points:
                            station_name = POINT_MAP.get(point, f"Unknown({point})")
                            total_tasks += 1
                            station_counts[station_name] = station_counts.get(station_name, 0) + 1
                            action_counts[action.upper()] += 1
                            hour_key = f"{time_str[12:14]}:00"
                            timeline_counts[hour_key] = timeline_counts.get(hour_key, 0) + 1
            
            self.agv_data_ready.emit({
                "stations": station_counts,
                "actions": action_counts,
                "timeline": dict(sorted(timeline_counts.items())),
                "total": total_tasks
            })
        except Exception as e: print("Lỗi đọc Logs:", e)

    def process_aoi(self):
        try:
            pass_count = fail_count = 0
            for folder in self.file_paths:
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        file_lower = file.lower()
                        if "all pass" in file_lower: pass_count += 1
                        elif "fail" in file_lower: fail_count += 1
            self.aoi_data_ready.emit(pass_count, fail_count)
        except Exception as e: print("Lỗi đọc AOI:", e)

# ==========================================
# 3. GIAO DIỆN CHÍNH (DARK MODE)
# ==========================================
class SmartFactoryDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Factory Dashboard - Tối ưu 3x3 (Dark Mode) - Smooth Hover")
        self.setGeometry(50, 50, 1366, 768)
        
        self.bg_dark = "#0a192f"
        self.panel_dark = "#112240"
        self.text_light = "#ccd6f6"
        self.accent_color = "#64ffda"
        self.setStyleSheet(f"background-color: {self.bg_dark}; color: {self.text_light};")
        
        self.oee_df = None 
        
        self.worker = DataWorker()
        self.worker.oee_data_ready.connect(self.handle_oee_data_ready)
        self.worker.agv_data_ready.connect(self.update_agv_dashboard)
        self.worker.aoi_data_ready.connect(self.update_aoi_cards)
        
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        grid = QGridLayout(central_widget)
        grid.setContentsMargins(15, 15, 15, 15)
        grid.setSpacing(15)

        # ROW 0
        ctrl_panel = self.create_panel()
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.addWidget(QLabel("<b>⚙️ HỆ THỐNG & DỮ LIỆU</b>"))
        
        self.btn_log = self.create_button("📜 Tải Logs AGV", "#0288d1")
        self.btn_aoi = self.create_button("🖼️ Thư Mục AOI", "#f57c00")
        
        oee_layout = QVBoxLayout()
        oee_layout.setSpacing(2)
        self.btn_oee = self.create_button("📊 Tải File OEE", "#7b1fa2")
        self.combo_oee_date = QComboBox()
        self.combo_oee_date.addItem("📅 Chọn ngày OEE (Tất cả)")
        self.combo_oee_date.setStyleSheet(f"""
            QComboBox {{ background-color: {self.bg_dark}; border: 1px solid #333; 
                        color: {self.text_light}; padding: 5px; border-radius: 4px; }}
            QComboBox::drop-down {{ border: none; }}
        """)
        self.combo_oee_date.currentTextChanged.connect(self.filter_oee_by_date)
        
        oee_layout.addWidget(self.btn_oee)
        oee_layout.addWidget(self.combo_oee_date)
        
        self.btn_log.clicked.connect(self.load_logs)
        self.btn_oee.clicked.connect(self.load_oee)
        self.btn_aoi.clicked.connect(self.load_aoi)
        
        ctrl_layout.addWidget(self.btn_log)
        ctrl_layout.addLayout(oee_layout)
        ctrl_layout.addWidget(self.btn_aoi)
        ctrl_layout.addStretch()
        grid.addWidget(ctrl_panel, 0, 0)

        self.agv_kpi_panel = self.create_panel()
        agv_kpi_layout = QVBoxLayout(self.agv_kpi_panel)
        self.lbl_agv_total = QLabel("0")
        self.lbl_agv_total.setStyleSheet(f"font-size: 40px; font-weight: bold; color: {self.accent_color};")
        self.lbl_agv_total.setAlignment(Qt.AlignCenter)
        self.lbl_agv_hot = QLabel("Trạm nhộn nhịp nhất: --")
        self.lbl_agv_hot.setAlignment(Qt.AlignCenter)
        agv_kpi_layout.addWidget(QLabel("<b>🔄 TỔNG NHIỆM VỤ AGV</b>", alignment=Qt.AlignCenter))
        agv_kpi_layout.addWidget(self.lbl_agv_total)
        agv_kpi_layout.addWidget(self.lbl_agv_hot)
        grid.addWidget(self.agv_kpi_panel, 0, 1)

        self.aoi_kpi_panel = self.create_panel()
        aoi_kpi_layout = QVBoxLayout(self.aoi_kpi_panel)
        self.lbl_aoi_rate = QLabel("0%")
        self.lbl_aoi_rate.setStyleSheet(f"font-size: 40px; font-weight: bold; color: #4CAF50;")
        self.lbl_aoi_rate.setAlignment(Qt.AlignCenter)
        self.lbl_aoi_total = QLabel("Tổng kiểm tra: 0 (Pass: 0 | Fail: 0)")
        self.lbl_aoi_total.setAlignment(Qt.AlignCenter)
        aoi_kpi_layout.addWidget(QLabel("<b>🖼️ TỶ LỆ AOI ĐẠT</b>", alignment=Qt.AlignCenter))
        aoi_kpi_layout.addWidget(self.lbl_aoi_rate)
        aoi_kpi_layout.addWidget(self.lbl_aoi_total)
        grid.addWidget(self.aoi_kpi_panel, 0, 2)

        # ROW 1 & 2 - Gắn sẵn Event Hover lúc khởi tạo Chart
        self.fig_agv_st, self.ax_agv_st, self.canvas_agv_st = self.create_dark_chart()
        grid.addWidget(self.canvas_agv_st, 1, 0)

        self.fig_agv_act, self.ax_agv_act, self.canvas_agv_act = self.create_dark_chart()
        grid.addWidget(self.canvas_agv_act, 1, 1)

        self.fig_agv_time, self.ax_agv_time, self.canvas_agv_time = self.create_dark_chart()
        grid.addWidget(self.canvas_agv_time, 1, 2)

        self.fig_f4, self.ax_f4, self.canvas_f4 = self.create_dark_chart()
        grid.addWidget(self.canvas_f4, 2, 0)
        
        self.fig_f5, self.ax_f5, self.canvas_f5 = self.create_dark_chart()
        grid.addWidget(self.canvas_f5, 2, 1)

        self.fig_pie, self.ax_pie, self.canvas_pie = self.create_dark_chart()
        grid.addWidget(self.canvas_pie, 2, 2)

        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 2)
        grid.setRowStretch(2, 2)

    def create_panel(self):
        panel = QFrame()
        panel.setStyleSheet(f"background-color: {self.panel_dark}; border-radius: 8px;")
        return panel

    def create_button(self, text, bg_color):
        btn = QPushButton(text)
        btn.setFont(QFont("Arial", 11, QFont.Bold))
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; color: white;
                border-radius: 5px; padding: 12px; border: none; margin: 2px; }}
            QPushButton:hover {{ background-color: {self.accent_color}; color: #000; }}
        """)
        return btn

    def create_dark_chart(self):
        fig = Figure()
        fig.patch.set_facecolor(self.panel_dark)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet(f"background-color: {self.panel_dark}; border-radius: 8px;")
        ax = fig.add_subplot(111)
        self.apply_dark_theme_to_ax(ax)
        
        # KẾT NỐI SỰ KIỆN HOVER TOÀN CỤC NGAY TỪ ĐẦU
        canvas.mpl_connect("motion_notify_event", self.on_hover)
        return fig, ax, canvas

    def apply_dark_theme_to_ax(self, ax):
        ax.set_facecolor(self.panel_dark)
        ax.tick_params(colors=self.text_light)
        ax.xaxis.label.set_color(self.text_light)
        ax.yaxis.label.set_color(self.text_light)
        ax.title.set_color(self.accent_color)
        for spine in ax.spines.values(): spine.set_edgecolor('#333333')

    # ==========================================
    # LOGIC HOVER TẬP TRUNG (KHÔNG BỊ LAG/FLICKER)
    # ==========================================
    def create_annotation(self, ax):
        annot = ax.annotate("", xy=(0,0), xytext=(0, 20), textcoords="offset points", 
                            ha='center', va='bottom', zorder=20, color=self.text_light,
                            bbox=dict(boxstyle="round,pad=0.5", fc="#0a192f", ec=self.accent_color, lw=1, alpha=0.9))
        annot.set_visible(False)
        annot.set_picker(False) # Cấm Tooltip giành quyền điều khiển chuột
        return annot

    def on_hover(self, event):
        ax = event.inaxes
        
        # Nếu chuột trượt ra ngoài, giấu MỌI tooltip hiện có để chống nhiễu
        for attr in ['ax_agv_st', 'ax_agv_act', 'ax_agv_time', 'ax_f4', 'ax_f5', 'ax_pie']:
            axis = getattr(self, attr, None)
            if axis and hasattr(axis, 'annot'):
                if axis != ax and axis.annot.get_visible():
                    axis.annot.set_visible(False)
                    axis.figure.canvas.draw_idle()

        # Nếu không nằm trong một trục biểu đồ hợp lệ, bỏ qua
        if ax is None or not hasattr(ax, 'annot'): return

        annot = ax.annot
        chart_type = getattr(ax, 'chart_type', None)
        if not chart_type: return

        is_over = False

        # --- XỬ LÝ BIỂU ĐỒ CỘT ---
        if chart_type == 'bar':
            for i, bar in enumerate(ax.bars):
                cont, _ = bar.contains(event)
                if cont:
                    val = bar.get_height()
                    if ax in [self.ax_f4, self.ax_f5]:
                        new_text = f" Line: {ax.labels[i]} \n OEE: {val:.1f}% "
                    else:
                        new_text = f" Trạm: {ax.labels[i]} \n Lượt: {int(val)} "
                    
                    if not annot.get_visible() or annot.get_text() != new_text:
                        annot.xy = (bar.get_x() + bar.get_width() / 2, val)
                        annot.set_text(new_text)
                        annot.set_visible(True)
                        event.canvas.draw_idle()
                    is_over = True
                    break

        # --- XỬ LÝ BIỂU ĐỒ TRÒN ---
        elif chart_type == 'pie':
            for i, wedge in enumerate(ax.wedges):
                cont, _ = wedge.contains(event)
                if cont:
                    val = ax.values[i]
                    total = sum(ax.values)
                    pct = (val/total*100) if total > 0 else 0
                    new_text = f" {ax.labels[i]}: {val} ({pct:.1f}%) "
                    
                    if not annot.get_visible() or annot.get_text() != new_text:
                        theta = math.radians((wedge.theta1 + wedge.theta2) / 2.0)
                        r = wedge.r / 2.0
                        x = r * math.cos(theta) + wedge.center[0]
                        y = r * math.sin(theta) + wedge.center[1]
                        annot.xy = (x, y)
                        annot.set_text(new_text)
                        annot.set_visible(True)
                        event.canvas.draw_idle()
                    is_over = True
                    break
                    
        # --- XỬ LÝ BIỂU ĐỒ ĐƯỜNG ---
        elif chart_type == 'line':
            cont, ind = ax.line.contains(event)
            if cont:
                idx = ind["ind"][0]
                x_pos = ax.line.get_xdata()[idx]
                y_pos = ax.line.get_ydata()[idx]
                new_text = f" Giờ: {ax.labels[idx]} \n Lượt: {ax.values[idx]} "
                
                if not annot.get_visible() or annot.get_text() != new_text:
                    annot.xy = (x_pos, y_pos)
                    annot.set_text(new_text)
                    annot.set_visible(True)
                    event.canvas.draw_idle()
                is_over = True

        # Tắt Tooltip nếu chuột không đè lên bất cứ cục dữ liệu nào
        if not is_over and annot.get_visible():
            annot.set_visible(False)
            event.canvas.draw_idle()

    # ==========================================
    # CÁC HÀM XỬ LÝ DỮ LIỆU CHÍNH
    # ==========================================
    def load_logs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn File Log", "", "Log Files (*.log *.txt)")
        if files:
            self.lbl_agv_total.setText("...")
            self.worker.task = "LOGS"
            self.worker.file_paths = files
            self.worker.start()

    def load_oee(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn File OEE", "", "Excel/CSV (*.xls *.xlsx *.csv)")
        if files:
            self.worker.task = "OEE"
            self.worker.file_paths = files
            self.worker.start()

    def load_aoi(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn Thư Mục AOI")
        if folder:
            self.worker.task = "AOI"
            self.worker.file_paths = [folder]
            self.worker.start()

    def handle_oee_data_ready(self, df):
        self.oee_df = df
        self.combo_oee_date.blockSignals(True)
        self.combo_oee_date.clear()
        self.combo_oee_date.addItem("📅 Chọn ngày OEE (Tất cả)")
        
        if df is not None and not df.empty and '日' in df.columns:
            dates = sorted(df['日'].dropna().unique())
            for d in dates: self.combo_oee_date.addItem(str(d))
                
        self.combo_oee_date.blockSignals(False)
        self.draw_oee_charts(df)

    def filter_oee_by_date(self, selected_date):
        if self.oee_df is None or self.oee_df.empty: return
        filtered_df = self.oee_df if "Tất cả" in selected_date else self.oee_df[self.oee_df['日'].astype(str) == selected_date]
        self.draw_oee_charts(filtered_df)

    def update_agv_dashboard(self, data):
        self.lbl_agv_total.setText(str(data['total']))
        filtered_stations = {k: v for k, v in data['stations'].items() if k != "PATH"}
        
        if filtered_stations:
            hot_station = max(filtered_stations, key=filtered_stations.get)
            self.lbl_agv_hot.setText(f"Trạm nhộn nhịp nhất: {hot_station} ({filtered_stations[hot_station]} lần)")

        # 1. Bar Chart: AGV Stations
        self.ax_agv_st.clear()
        self.apply_dark_theme_to_ax(self.ax_agv_st)
        if filtered_stations:
            sorted_st = dict(sorted(filtered_stations.items(), key=lambda item: item[1], reverse=True)[:10])
            st_names = list(sorted_st.keys())
            st_values = list(sorted_st.values())
            
            bars = self.ax_agv_st.bar(st_names, st_values, color="#3498db")
            self.ax_agv_st.set_title("Top Trạm Hoạt Động (AGV)", pad=10)
            self.ax_agv_st.tick_params(axis='x', rotation=30, labelsize=8)
            
            # Gắn Dữ Liệu Tooltip Vào AX
            self.ax_agv_st.annot = self.create_annotation(self.ax_agv_st)
            self.ax_agv_st.bars = bars
            self.ax_agv_st.labels = st_names
            self.ax_agv_st.chart_type = 'bar'
            
        self.fig_agv_st.tight_layout()
        self.canvas_agv_st.draw()

        # 2. Pie Chart: AGV UP/DOWN
        self.ax_agv_act.clear()
        self.apply_dark_theme_to_ax(self.ax_agv_act)
        if sum(data['actions'].values()) > 0:
            labels = list(data['actions'].keys())
            sizes = list(data['actions'].values())
            colors = ['#4CAF50', '#F44336']
            wedges, texts, autotexts = self.ax_agv_act.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            self.ax_agv_act.set_title("Tỷ Lệ Lấy/Trả Hàng (UP/DOWN)", pad=10)
            for text in texts: text.set_color(self.text_light)
            for autotext in autotexts: autotext.set_color('white')
            
            # Gắn Dữ Liệu Tooltip Vào AX
            self.ax_agv_act.annot = self.create_annotation(self.ax_agv_act)
            self.ax_agv_act.wedges = wedges
            self.ax_agv_act.labels = labels
            self.ax_agv_act.values = sizes
            self.ax_agv_act.chart_type = 'pie'

        self.fig_agv_act.tight_layout()
        self.canvas_agv_act.draw()

        # 3. Line Chart: AGV Timeline
        self.ax_agv_time.clear()
        self.apply_dark_theme_to_ax(self.ax_agv_time)
        if data['timeline']:
            hours = list(data['timeline'].keys())
            counts = list(data['timeline'].values())
            
            # ĐÃ THÊM PICKER=5 GIÚP HIT-BOX HOVER TO HƠN, DỄ DI CHUỘT HƠN NHIỀU
            lines = self.ax_agv_time.plot(hours, counts, marker='o', markersize=6, color=self.accent_color, linewidth=2, picker=5)
            self.ax_agv_time.fill_between(hours, counts, color=self.accent_color, alpha=0.2)
            self.ax_agv_time.set_title("Lưu Lượng Hoạt Động AGV Theo Giờ", pad=10)
            self.ax_agv_time.tick_params(axis='x', rotation=45, labelsize=8)
            self.ax_agv_time.grid(color='#333333', linestyle='--', linewidth=0.5, alpha=0.5)
            
            # Gắn Dữ Liệu Tooltip Vào AX
            self.ax_agv_time.annot = self.create_annotation(self.ax_agv_time)
            self.ax_agv_time.line = lines[0]
            self.ax_agv_time.labels = hours
            self.ax_agv_time.values = counts
            self.ax_agv_time.chart_type = 'line'

        self.fig_agv_time.tight_layout()
        self.canvas_agv_time.draw()

    def update_aoi_cards(self, pass_count, fail_count):
        total = pass_count + fail_count
        pass_rate = (pass_count/total*100) if total > 0 else 0
        self.lbl_aoi_rate.setText(f"{pass_rate:.1f}%")
        self.lbl_aoi_rate.setStyleSheet(f"font-size: 40px; font-weight: bold; color: {'#4CAF50' if pass_rate >= 90 else '#F44336'};")
        self.lbl_aoi_total.setText(f"Tổng kiểm tra: {total} (Pass: {pass_count} | Fail: {fail_count})")
        
        # Pie Chart: AOI
        self.ax_pie.clear()
        self.apply_dark_theme_to_ax(self.ax_pie)
        if total > 0:
            labels = ['PASS', 'FAIL']
            sizes = [pass_count, fail_count]
            colors = ['#4CAF50', '#F44336']
            wedges, texts, autotexts = self.ax_pie.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            self.ax_pie.set_title("Chi Tiết Chất Lượng AOI", pad=10)
            for text in texts: text.set_color(self.text_light)
            for autotext in autotexts: autotext.set_color('white')
            
            # Gắn Dữ Liệu Tooltip Vào AX
            self.ax_pie.annot = self.create_annotation(self.ax_pie)
            self.ax_pie.wedges = wedges
            self.ax_pie.labels = labels
            self.ax_pie.values = sizes
            self.ax_pie.chart_type = 'pie'

        self.fig_pie.tight_layout()
        self.canvas_pie.draw()

    def draw_oee_charts(self, df):
        self.ax_f4.clear()
        self.ax_f5.clear()
        self.apply_dark_theme_to_ax(self.ax_f4)
        self.apply_dark_theme_to_ax(self.ax_f5)
        
        if df is not None and not df.empty and 'OEE_Num' in df.columns:
            # Bar Chart: OEE Tầng 4
            df_f4 = df[df['樓層'] == 'F4'] if '樓層' in df.columns else pd.DataFrame()
            if not df_f4.empty:
                avg_f4 = df_f4.groupby('綫')['OEE_Num'].mean().dropna()
                lines_f4 = list(avg_f4.index)
                vals_f4 = list(avg_f4.values)
                
                bars_f4 = self.ax_f4.bar(lines_f4, vals_f4, color='#9b59b6')
                self.ax_f4.set_title("Chỉ Số OEE - Tầng 4", pad=10)
                self.ax_f4.set_ylim(0, 105)
                
                self.ax_f4.annot = self.create_annotation(self.ax_f4)
                self.ax_f4.bars = bars_f4
                self.ax_f4.labels = lines_f4
                self.ax_f4.chart_type = 'bar'

            # Bar Chart: OEE Tầng 5
            df_f5 = df[df['樓層'] == 'F5'] if '樓層' in df.columns else pd.DataFrame()
            if not df_f5.empty:
                avg_f5 = df_f5.groupby('綫')['OEE_Num'].mean().dropna()
                lines_f5 = list(avg_f5.index)
                vals_f5 = list(avg_f5.values)
                
                bars_f5 = self.ax_f5.bar(lines_f5, vals_f5, color='#e67e22')
                self.ax_f5.set_title("Chỉ Số OEE - Tầng 5", pad=10)
                self.ax_f5.set_ylim(0, 105)
                
                self.ax_f5.annot = self.create_annotation(self.ax_f5)
                self.ax_f5.bars = bars_f5
                self.ax_f5.labels = lines_f5
                self.ax_f5.chart_type = 'bar'

        self.fig_f4.tight_layout()
        self.canvas_f4.draw()
        self.fig_f5.tight_layout()
        self.canvas_f5.draw()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SmartFactoryDashboard()
    window.showMaximized()
    sys.exit(app.exec_())