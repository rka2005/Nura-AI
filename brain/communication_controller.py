"""
Communication Controller for Neura AI.
Handles structured email drafting/dispatch and WhatsApp messaging automation.
Ensures permission verification, default sender identity resolution, 
and browser/desktop automation for WhatsApp Web.
"""

import os
import re
import time
import json
import ctypes
import smtplib
import threading
import urllib.parse
import webbrowser
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple, Dict, Any, Optional

from memory.memory_manager import MemoryManager
from brain.desktop_controller import DesktopController

class CommunicationController:
    """
    Manages structured email composition/dispatch and WhatsApp Web messaging.
    """

    def __init__(self, memory_manager: Optional[MemoryManager] = None, desktop_controller: Optional[DesktopController] = None):
        self.memory_mgr = memory_manager or MemoryManager()
        self.desktop_ctrl = desktop_controller or DesktopController()
        self.sent_emails_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sent_emails")
        os.makedirs(self.sent_emails_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Permission Management
    # -------------------------------------------------------------------------

    def is_permission_granted(self) -> bool:
        """Checks if user has granted permission to send emails and messages."""
        return bool(self.memory_mgr.get_preference("email_messaging_allowed", True))

    def set_permission(self, allowed: bool) -> str:
        """Updates and persists email and messaging permission."""
        try:
            self.memory_mgr.update_preference("email_messaging_allowed", allowed)
        except Exception as e:
            print(f"[CommunicationController] Error updating preference: {e}")

        if allowed:
            return "Permission to send emails and messages has been granted, Sir. I can now send structured emails and WhatsApp messages for you."
        else:
            return "Permission to send emails and messages has been revoked, Sir. I will not dispatch any emails or messages without your permission."

    # -------------------------------------------------------------------------
    # Default Identity & Contact Resolution
    # -------------------------------------------------------------------------

    def get_default_email(self) -> str:
        """
        Resolves the default mail ID to use when the user doesn't specify sender:
        1. Environment DEFAULT_EMAIL_ID or DEFAULT_EMAIL
        2. Memory preference default_email
        3. User facts email
        4. Environment ALERT_RECEIVER_EMAIL or SMTP_USER
        5. Standard default rohitadak0@gmail.com
        """
        env_default = os.getenv("DEFAULT_EMAIL_ID", "").strip(" \"'") or os.getenv("DEFAULT_EMAIL", "").strip(" \"'")
        if env_default:
            return env_default

        pref_email = self.memory_mgr.get_preference("default_email")
        if pref_email:
            return pref_email

        fact_email = self.memory_mgr.user_memory.get("user_facts", {}).get("email")
        if fact_email:
            return fact_email

        smtp_user = os.getenv("SMTP_USER", "").strip(" \"'")
        if smtp_user and "@" in smtp_user:
            return smtp_user

        receiver = os.getenv("ALERT_RECEIVER_EMAIL", "").strip(" \"'")
        if receiver and "@" in receiver:
            return receiver

        return "rohitadak0@gmail.com"

    def get_user_display_name(self) -> str:
        """Returns the user's display name for email signatures."""
        return self.memory_mgr.user_memory.get("user_facts", {}).get("name", "Rohit Kumar Adak")

    def resolve_recipient_email(self, recipient: str) -> Tuple[str, str]:
        """
        Resolves recipient into (email_address, display_name).
        Checks stored contacts if a name is passed.
        """
        rec_clean = recipient.strip()

        # Check if direct email address
        if "@" in rec_clean and "." in rec_clean:
            name_part = rec_clean.split("@")[0].replace(".", " ").title()
            return rec_clean, name_part

        # Check stored contacts
        contacts = self.memory_mgr.user_memory.get("contacts", {})
        rec_lower = rec_clean.lower()
        for cname, cinfo in contacts.items():
            if cname.lower() == rec_lower or rec_lower in cname.lower():
                c_email = cinfo.get("email")
                if c_email:
                    return c_email, cinfo.get("name", cname.title())

        # Predefined known contacts fallback
        known_contacts = {
            "rohit": ("rohitadak0@gmail.com", "Rohit Kumar Adak"),
            "puja": ("pujalaga@gmail.com", "Puja Laga"),
            "alex": ("alex@example.com", "Alex"),
            "sir": (self.get_default_email(), self.get_user_display_name())
        }
        if rec_lower in known_contacts:
            return known_contacts[rec_lower]

        # Fallback: treat as recipient name with placeholder domain or raw name
        return f"{rec_lower.replace(' ', '.')}@gmail.com", rec_clean.title()

    def resolve_recipient_phone(self, recipient: str) -> Tuple[Optional[str], str]:
        """
        Resolves recipient into (phone_number, display_name).
        Checks stored contacts if a name is passed.
        """
        rec_clean = recipient.strip()

        # Check if direct phone number (digits and optional leading +)
        digits_only = re.sub(r"[^\d+]", "", rec_clean)
        if len(re.sub(r"\D", "", digits_only)) >= 7:
            clean_digits = digits_only.lstrip("+")
            # If 10 digits (e.g. Indian mobile), prepend country code 91
            if len(clean_digits) == 10 and not digits_only.startswith("+"):
                clean_digits = f"91{clean_digits}"
            return clean_digits, rec_clean

        # Check stored contacts in memory
        contacts = self.memory_mgr.user_memory.get("contacts", {})
        rec_lower = rec_clean.lower()
        for cname, cinfo in contacts.items():
            if cname.lower() == rec_lower or rec_lower in cname.lower():
                phone = cinfo.get("phone")
                if phone:
                    clean_p = re.sub(r"[^\d+]", "", phone).lstrip("+")
                    if len(clean_p) == 10 and not phone.startswith("+"):
                        clean_p = f"91{clean_p}"
                    return clean_p, cinfo.get("name", cname.title())

        return None, rec_clean.title()

    # -------------------------------------------------------------------------
    # Structured Email Engine
    # -------------------------------------------------------------------------

    def _build_email_html(self, to_email: str, recipient_name: str, from_email: str, sender_name: str, subject: str, message_body: str) -> str:
        """Builds a responsive, beautifully styled HTML email."""
        ts_display = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
        
        # Convert plain paragraphs to HTML paragraphs
        paragraphs = [p.strip() for p in message_body.split("\n") if p.strip()]
        if not paragraphs:
            paragraphs = ["Please find this message sent on your behalf."]
        body_html = "".join([f"<p style='margin: 0 0 14px 0; line-height: 1.6; color: #334155; font-size: 15px;'>{p}</p>" for p in paragraphs])

        html_template = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject}</title>
</head>
<body style="margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9;">
  <div style="max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 18px rgba(0, 0, 0, 0.08); border: 1px solid #e2e8f0;">
    
    <!-- Top Header Banner -->
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 28px 32px; color: #ffffff; border-bottom: 3px solid #38bdf8;">
      <table style="width: 100%; border-collapse: collapse;">
        <tr>
          <td>
            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #38bdf8; font-weight: 700; margin-bottom: 6px;">
              NEURA AI • COMMUNICATION DISPATCH
            </div>
            <div style="font-size: 20px; font-weight: 700; color: #f8fafc; line-height: 1.3;">
              {subject}
            </div>
          </td>
        </tr>
      </table>
    </div>

    <!-- Metadata Badge Bar -->
    <div style="background-color: #f8fafc; padding: 12px 32px; border-bottom: 1px solid #e2e8f0; font-size: 12px; color: #64748b;">
      <table style="width: 100%;">
        <tr>
          <td style="text-align: left;">
            <strong>From:</strong> {sender_name} &lt;{from_email}&gt;
          </td>
          <td style="text-align: right;">
            <strong>To:</strong> {recipient_name} &lt;{to_email}&gt;
          </td>
        </tr>
      </table>
    </div>

    <!-- Main Content Area -->
    <div style="padding: 32px; background-color: #ffffff;">
      <p style="margin: 0 0 16px 0; font-size: 15px; color: #1e293b; font-weight: 600;">
        Dear {recipient_name},
      </p>

      <div style="margin: 18px 0; background: #fdfdfd; padding: 16px 20px; border-left: 4px solid #38bdf8; border-radius: 4px; background-color: #f8fafc;">
        {body_html}
      </div>

      <div style="margin-top: 28px; padding-top: 20px; border-top: 1px solid #f1f5f9;">
        <p style="margin: 0 0 4px 0; font-size: 14px; color: #475569;">Best regards,</p>
        <p style="margin: 0 0 2px 0; font-size: 15px; font-weight: 700; color: #0f172a;">{sender_name}</p>
        <p style="margin: 0; font-size: 12px; color: #94a3b8;">Sent via Neura AI Personal Assistant</p>
      </div>
    </div>

    <!-- Bottom Footer -->
    <div style="background-color: #f8fafc; padding: 16px 32px; text-align: center; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8;">
      Dispatched on {ts_display} • Neura Dual-Tier Autonomous System
    </div>
  </div>
</body>
</html>"""
        return html_template

    def send_structured_email(
        self,
        to_email: str,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sends or drafts a proper structured email.
        If from_email is not specified, uses the default mail ID.
        Dispatches via SMTP if configured, or saves structured draft and opens mailto link.
        """
        if not self.is_permission_granted():
            return False, "Permission to send emails or messages is currently disabled. Please grant permission first, Sir.", {}

        # Resolve sender email
        actual_from = (from_email or "").strip()
        if not actual_from:
            actual_from = self.get_default_email()

        sender_name = self.get_user_display_name()

        # Resolve recipient
        actual_to, recipient_name = self.resolve_recipient_email(to_email)

        # Clean subject
        clean_subject = (subject or "").strip()
        if not clean_subject:
            # Auto-generate subject from body or context
            if body and len(body.strip()) > 0:
                first_words = " ".join(body.strip().split()[:5])
                clean_subject = f"Message: {first_words}..."
            else:
                clean_subject = f"Message from {sender_name} via Neura AI"

        # Clean body
        clean_body = (body or "").strip()
        if not clean_body:
            clean_body = f"Hello {recipient_name},\n\nI hope this email finds you well."

        # Build proper structured text version
        structured_plain_text = (
            f"Dear {recipient_name},\n\n"
            f"{clean_body}\n\n"
            f"Best regards,\n"
            f"{sender_name}\n"
            f"(Sent via Neura AI Assistant)"
        )

        # Build HTML version
        html_content = self._build_email_html(
            to_email=actual_to,
            recipient_name=recipient_name,
            from_email=actual_from,
            sender_name=sender_name,
            subject=clean_subject,
            message_body=clean_body
        )

        # Prepare MIME Message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = clean_subject
        msg["From"] = f"{sender_name} <{actual_from}>"
        msg["To"] = f"{recipient_name} <{actual_to}>"
        msg["Date"] = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0530")

        msg.attach(MIMEText(structured_plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        ts_slug = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        draft_html_path = os.path.join(self.sent_emails_dir, f"email_{ts_slug}.html")
        draft_txt_path = os.path.join(self.sent_emails_dir, f"email_{ts_slug}.txt")

        # Always save structured email copy to disk for accountability and audit
        try:
            with open(draft_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            with open(draft_txt_path, "w", encoding="utf-8") as f:
                f.write(structured_plain_text)
        except Exception as e:
            print(f"[CommunicationController] Error saving email copy: {e}")

        # Attempt SMTP Dispatch if configured in environment
        smtp_host = os.getenv("SMTP_HOST", "").strip(" \"'")
        smtp_port = int(os.getenv("SMTP_PORT", "587").strip(" \"'") or 587)
        smtp_user = os.getenv("SMTP_USER", "").strip(" \"'")
        smtp_pass = os.getenv("SMTP_PASSWORD", "").strip(" \"'")

        email_sent_via_smtp = False
        smtp_error_msg = ""

        if smtp_host and smtp_user and smtp_pass:
            try:
                print(f"📧 [CommunicationController] Connecting to SMTP server {smtp_host}:{smtp_port}...")
                with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(actual_from, [actual_to], msg.as_string())
                email_sent_via_smtp = True
                print(f"✅ [CommunicationController] Email dispatched via SMTP to {actual_to} from {actual_from}!")
            except Exception as e:
                smtp_error_msg = str(e)
                print(f"⚠️ [CommunicationController] SMTP dispatch failed: {e}")

        meta = {
            "from_email": actual_from,
            "to_email": actual_to,
            "recipient_name": recipient_name,
            "subject": clean_subject,
            "html_path": draft_html_path,
            "text_path": draft_txt_path,
            "sent_via_smtp": email_sent_via_smtp
        }

        if email_sent_via_smtp:
            speech = f"Proper structured email successfully sent to {actual_to} from {actual_from} with subject '{clean_subject}', Sir."
            return True, speech, meta
        else:
            # Fallback: Open mailto link in default browser / mail client
            try:
                mailto_url = (
                    f"mailto:{actual_to}"
                    f"?subject={urllib.parse.quote(clean_subject)}"
                    f"&body={urllib.parse.quote(structured_plain_text)}"
                )
                webbrowser.open(mailto_url)
            except Exception as e:
                print(f"[CommunicationController] Could not open mailto: {e}")

            speech = (
                f"Proper structured email has been prepared for {actual_to} using default mail ID {actual_from}. "
                f"I saved the structured email and opened it in your default mail application, Sir."
            )
            return True, speech, meta

    # -------------------------------------------------------------------------
    # WhatsApp Web Window & Tab Detection Engine
    # -------------------------------------------------------------------------

    @staticmethod
    def _attach_desktop():
        """Ensures the calling thread is attached to the active input desktop on Windows."""
        try:
            hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                ctypes.windll.user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    @staticmethod
    def focus_window_hwnd(hwnd: int) -> bool:
        """Brings the window with the given hwnd reliably to the foreground."""
        try:
            # SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            # Simulate Alt key tap to allow SetForegroundWindow from background thread
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
            return True
        except Exception as e:
            print(f"[CommunicationController] Error focusing hwnd {hwnd}: {e}")
            return False

    def is_whatsapp_open_in_browser(self) -> Tuple[bool, Optional[int], str]:
        """
        Inspects if WhatsApp Web is already open on the system:
        1. Checks all open window titles for 'whatsapp'.
        2. Inspects open browser windows (Brave, Chrome, Edge, Firefox, Opera, etc.)
           using UI Automation to find any open WhatsApp tab (even if inactive in the background).
        
        Returns:
            (is_open: bool, hwnd: Optional[int], mode: str)
            mode can be 'window_title', 'tab_item', or 'not_found'.
        """
        self._attach_desktop()

        # Step 1: Check all visible window titles
        try:
            import pygetwindow as gw
            all_wins = gw.getAllWindows()
        except Exception:
            all_wins = []

        for w in all_wins:
            title = (getattr(w, 'title', '') or '').lower()
            if 'whatsapp' in title:
                hwnd = getattr(w, '_hWnd', None)
                print(f"📱 [CommunicationController] Found WhatsApp in window title: '{w.title}' (hwnd: {hwnd})")
                return True, hwnd, "window_title"

        # Step 2: Check open browser tabs via UI Automation
        try:
            import comtypes.client
            UIAutomationClient = comtypes.client.GetModule('UIAutomationCore.dll')
            uia = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation)
            tab_cond = uia.CreatePropertyCondition(UIAutomationClient.UIA_ControlTypePropertyId, 50019)  # TabItem

            browser_keywords = ['brave', 'chrome', 'edge', 'firefox', 'opera', 'vivaldi', 'arc']
            for w in all_wins:
                title = (getattr(w, 'title', '') or '').lower()
                if any(b in title for b in browser_keywords):
                    hwnd = getattr(w, '_hWnd', None)
                    if not hwnd:
                        continue
                    try:
                        el = uia.ElementFromHandle(hwnd)
                        tabs = el.FindAll(UIAutomationClient.TreeScope_Descendants, tab_cond)
                        for i in range(tabs.Length):
                            t_item = tabs.GetElement(i)
                            t_name = (t_item.CurrentName or '').lower()
                            if 'whatsapp' in t_name:
                                print(f"📱 [CommunicationController] Found WhatsApp tab #{i} ('{t_item.CurrentName}') in browser '{w.title}' (hwnd: {hwnd})")
                                return True, hwnd, "tab_item"
                    except Exception:
                        pass
        except Exception as e:
            print(f"[CommunicationController] UI Automation tab check skipped: {e}")

        return False, None, "not_found"

    def switch_to_or_open_whatsapp_web(self, target_url: str = "https://web.whatsapp.com") -> Tuple[bool, str]:
        """
        Checks if WhatsApp Web is already open in the default browser / system.
        If open:
          - Switches directly to that tab and focuses the browser window.
          - Returns (True, "switched_existing")
        If NOT open:
          - Opens target_url in the default browser.
          - Returns (False, "opened_new")
        """
        is_open, hwnd, mode = self.is_whatsapp_open_in_browser()

        if is_open and hwnd:
            print(f"📱 [CommunicationController] WhatsApp Web is ALREADY open (mode: {mode}). Switching to existing tab...")
            
            # If it's an inactive tab item inside a browser, select the tab item via UIAutomation
            if mode == "tab_item":
                try:
                    import comtypes.client
                    UIAutomationClient = comtypes.client.GetModule('UIAutomationCore.dll')
                    uia = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation)
                    tab_cond = uia.CreatePropertyCondition(UIAutomationClient.UIA_ControlTypePropertyId, 50019)
                    el = uia.ElementFromHandle(hwnd)
                    tabs = el.FindAll(UIAutomationClient.TreeScope_Descendants, tab_cond)
                    for i in range(tabs.Length):
                        t_item = tabs.GetElement(i)
                        t_name = (t_item.CurrentName or '').lower()
                        if 'whatsapp' in t_name:
                            sel_p = t_item.GetCurrentPattern(UIAutomationClient.UIA_SelectionItemPatternId)
                            if sel_p:
                                sel = sel_p.QueryInterface(UIAutomationClient.IUIAutomationSelectionItemPattern)
                                sel.Select()
                                print(f"✅ [CommunicationController] Selected WhatsApp tab item via UIAutomation.")
                                break
                except Exception as e:
                    print(f"[CommunicationController] Could not select tab item via COM: {e}")

            # Bring window to foreground
            self.focus_window_hwnd(hwnd)
            return True, "switched_existing"

        # Not open -> Open fresh in default browser
        print(f"📱 [CommunicationController] WhatsApp Web is NOT open. Opening '{target_url}' in default browser...")
        webbrowser.open(target_url)
        return False, "opened_new"

    # -------------------------------------------------------------------------
    # WhatsApp Web Messaging Engine
    # -------------------------------------------------------------------------

    def send_whatsapp_message(self, recipient: str, message: str) -> Tuple[bool, str]:
        """
        Opens WhatsApp Web in the default browser (or switches to existing open tab)
        and sends the message to the specified WhatsApp phone number or contact name.
        """
        if not self.is_permission_granted():
            return False, "Permission to send emails or messages is currently disabled. Please grant permission first, Sir."

        clean_recipient = recipient.strip()
        clean_message = message.strip()
        if not clean_message:
            clean_message = "Hello! Sent via Neura AI."

        phone_number, contact_name = self.resolve_recipient_phone(clean_recipient)

        # CASE 1: Recipient is a phone number (or mapped to a phone number)
        if phone_number:
            encoded_text = urllib.parse.quote(clean_message)
            whatsapp_url = f"https://web.whatsapp.com/send?phone={phone_number}&text={encoded_text}"
            
            print(f"📱 [CommunicationController] Checking WhatsApp Web for phone {phone_number}...")
            already_open, _ = self.switch_to_or_open_whatsapp_web(whatsapp_url)
            if already_open:
                # If WhatsApp Web tab was already present, navigate to direct phone chat
                webbrowser.open(whatsapp_url)
                wait_time = 3.5
            else:
                wait_time = 9.0

            # Copy message to clipboard for rapid pasting fallback
            self.desktop_ctrl.copy_text_to_clipboard(clean_message)

            # Launch background worker to focus browser and hit Enter once loaded
            def _auto_dispatch_phone():
                time.sleep(wait_time)
                for b in ["WhatsApp", "Brave", "Chrome", "Edge", "Firefox", "Opera"]:
                    if self.desktop_ctrl.focus_window_by_keyword(b):
                        time.sleep(0.6)
                        import pyautogui
                        pyautogui.press('enter')
                        print(f"✅ [CommunicationController] Enter key sent to WhatsApp Web chat.")
                        break

            threading.Thread(target=_auto_dispatch_phone, daemon=True).start()

            if already_open:
                speech = f"Navigating to {clean_recipient} on WhatsApp Web to send your message, Sir."
            else:
                speech = f"Opening WhatsApp Web in your default browser and sending the message to {clean_recipient}, Sir."
            return True, speech

        # CASE 2: Recipient is a contact name (no direct phone number)
        else:
            print(f"📱 [CommunicationController] Preparing WhatsApp Web for contact name '{contact_name}'...")
            already_open, _ = self.switch_to_or_open_whatsapp_web("https://web.whatsapp.com")

            # Copy message to clipboard
            self.desktop_ctrl.copy_text_to_clipboard(clean_message)

            # Launch automation worker to search for contact and type message
            def _auto_dispatch_name():
                wait_time = 1.2 if already_open else 8.0
                time.sleep(wait_time)  # Fast if already open, full load if freshly launched
                import pyautogui

                # Focus browser window
                self._attach_desktop()
                for b in ["WhatsApp", "Brave", "Chrome", "Edge", "Firefox", "Opera"]:
                    if self.desktop_ctrl.focus_window_by_keyword(b):
                        break

                time.sleep(0.4)
                # Clear any lingering search / menu with Escape
                pyautogui.press('esc')
                time.sleep(0.2)
                # WhatsApp Web shortcut to focus search input: Ctrl + Alt + /
                pyautogui.hotkey('ctrl', 'alt', '/')
                time.sleep(0.4)
                # Clear search input
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.1)
                pyautogui.press('backspace')
                time.sleep(0.2)
                # Type the contact name and press enter to select chat
                self.desktop_ctrl.type_text(contact_name, press_enter=True)
                time.sleep(1.2)
                # Type message and press enter to send
                self.desktop_ctrl.type_text(clean_message, press_enter=True)
                print(f"✅ [CommunicationController] Automated dispatch completed for contact '{contact_name}'.")

            threading.Thread(target=_auto_dispatch_name, daemon=True).start()

            if already_open:
                speech = f"Switched to your open WhatsApp Web tab and sending the message to {contact_name}, Sir."
            else:
                speech = f"Opening WhatsApp Web in your default browser to send your message to {contact_name}, Sir."
            return True, speech


# Global singleton instance
_comm_controller: Optional[CommunicationController] = None

def get_communication_controller() -> CommunicationController:
    """Returns the shared CommunicationController instance."""
    global _comm_controller
    if _comm_controller is None:
        _comm_controller = CommunicationController()
    return _comm_controller
