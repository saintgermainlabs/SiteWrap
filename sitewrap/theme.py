# Copied from ToolBox (devtoolbox/theme.py, via MultiTerm) so SiteWrap looks the same.
class Theme:
    DARK_QSS = """
    QMainWindow {
        background-color: #1e1e2e;
        color: #cdd6f4;
    }
    QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: 'Inter', 'Segoe UI', sans-serif;
        font-size: 13px;
    }

    /* Tab Widget Styling */
    QTabWidget::pane {
        border: 1px solid #313244;
        background: #1e1e2e;
        border-radius: 6px;
    }
    QTabBar::tab {
        background: #181825;
        color: #a6adc8;
        padding: 10px 24px;
        margin-right: 4px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: bold;
    }
    QTabBar::tab:selected {
        background: #313244;
        color: #89b4fa;
        border-bottom: 2px solid #89b4fa;
    }
    QTabBar::tab:hover {
        background: #313244;
        color: #cdd6f4;
    }

    /* Card Frame Styling */
    QFrame.ServiceCard {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 10px;
        padding: 16px;
    }
    QFrame.ServiceCard:hover {
        border: 1px solid #89b4fa;
        background-color: #1e1e2e;
    }

    /* Primary & Secondary Buttons */
    QPushButton {
        background-color: #313244;
        color: #cdd6f4;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #45475a;
        color: #ffffff;
    }
    QPushButton:pressed {
        background-color: #585b70;
    }

    QPushButton.PrimaryBtn {
        background-color: #89b4fa;
        color: #11111b;
    }
    QPushButton.PrimaryBtn:hover {
        background-color: #b4befe;
    }

    QPushButton.ActionBtn {
        background-color: #313244;
        border: 1px solid #45475a;
        color: #cdd6f4;
    }
    QPushButton.ActionBtn:hover {
        background-color: #89b4fa;
        color: #11111b;
    }

    /* Input Fields */
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 6px;
        padding: 8px;
        color: #cdd6f4;
    }
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid #89b4fa;
    }

    /* Scrollbars */
    QScrollBar:vertical {
        border: none;
        background: #181825;
        width: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #45475a;
        border-radius: 4px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background: #585b70;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* Status bar (bottom-right Tailscale on/off toggle) */
    QStatusBar {
        background-color: #181825;
        border-top: 1px solid #313244;
        color: #a6adc8;
    }
    QStatusBar QLabel {
        color: #a6adc8;
    }
    """

    # ToolBox shell additions (sidebar nav), same Catppuccin palette.
    SHELL_QSS = DARK_QSS + """
    QListWidget#ModuleNav {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 6px;
        padding: 6px;
        outline: 0;
    }
    QListWidget#ModuleNav::item {
        padding: 10px 12px;
        border-radius: 6px;
        color: #a6adc8;
        font-weight: bold;
    }
    QListWidget#ModuleNav::item:selected {
        background: #313244;
        color: #89b4fa;
    }
    QListWidget#ModuleNav::item:hover {
        background: #313244;
        color: #cdd6f4;
    }
    QFrame.ServiceCard QLabel { background: transparent; }
    """
