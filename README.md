# 🚀 SessionKeeper Pro (v2.0)
> **Trình quản lý và khôi phục phiên làm việc chuyên nghiệp cho Kỹ sư & Văn phòng trên Windows 10 & 11.**

[![Windows](https://img.shields.io/badge/OS-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)](https://microsoft.com)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📌 Giới thiệu
**SessionKeeper Pro** là phần mềm tự động ghi nhớ và khôi phục toàn bộ môi trường làm việc khi bạn tắt máy hoặc bật lại. Được thiết kế tối ưu hóa đặc biệt cho kỹ sư trắc địa, địa chính và văn phòng thường xuyên xử lý các dự án nặng với hàng chục bản vẽ và bảng tính cùng lúc.

---

## ✨ Tính năng nổi bật
* **Quét chính xác từng tab bản vẽ CAD**: Hỗ trợ nhận diện các tab bản vẽ đang mở trong **AutoCAD** (`.dwg`, `.dxf`) thông qua cửa sổ tác vụ thời gian thực, không gây trùng lặp, không kéo file rác/file lock tạm `.dwl`.
* **Hỗ trợ MicroStation V8i**: Tự động nhận diện tài liệu `.dgn` đang mở và vị trí làm việc.
* **Xử lý thông minh Excel & Word**: Ghi nhớ chính xác file bảng tính Excel (`.xlsx`, `.xls`) đang mở, loại bỏ hoàn toàn thẻ ứng dụng rỗng trùng lặp.
* **Trình duyệt & Ứng dụng chat**: Tự động khôi phục toàn bộ tab đang mở trên **Google Chrome**, **Microsoft Edge**, và **Zalo PC**.
* **Nhớ thư mục & Layout cửa sổ**: Khôi phục lại đúng các thư mục Explorer và vị trí/kích thước cửa sổ trên màn hình.
* **Tiết kiệm pin & Siêu nhẹ (0% CPU khi chạy nền)**:
  - Sử dụng cơ chế bắt phím tắt Windows Event-Driven `GetMessageW` không tiêu tốn CPU.
  - Bộ quét đơn lượt Sub-100ms chạy ngầm độc lập (Non-blocking Async Worker).
  - Tương thích mượt mà từ máy cấu hình yếu/văn phòng đến máy trạm Workstation cấu hình cao trên cả **Windows 10** và **Windows 11**.
* **Tự động sao lưu ngầm (Auto-Snapshot)**: Tự động lưu sau mỗi 10 phút, không bao giờ lo mất phiên làm việc khi mất điện hoặc máy tính khởi động lại đột ngột.
* **Quản lý Hồ Sơ Dự Án**: Lưu riêng từng bộ hồ sơ theo từng công trình (Dự án Long Bình, Dự án Cát Lái...) để mở nhanh chỉ với 1 cú click.

---

## ⌨️ Phím tắt toàn cục (Global Hotkeys)
| Phím tắt | Chức năng |
| :--- | :--- |
| `Ctrl + Alt + S` | **Lưu nhanh phiên hiện tại (Quick Save)** |
| `Ctrl + Alt + R` | **Khôi phục toàn bộ ứng dụng và bản vẽ** |
| `Ctrl + Alt + H` | **Lưu phiên & Ngủ đông máy tính tức thì (0W điện)** |

---

## 🛠️ Cài đặt & Sử dụng
1. Tải bản Portable mới nhất `SessionKeeper_v2.0_Portable.zip` từ mục **Releases**.
2. Giải nén vào bất kỳ thư mục nào (ví dụ `D:\PhanMem\SessionKeeper` hoặc `C:\SessionKeeper`).
3. Chạy trực tiếp **`SessionKeeper.exe`** (Ứng dụng dạng Portable độc lập, không cần cài đặt Python hay phần mềm phụ trợ).
4. *(Tùy chọn)* Bật công tắc **"Tự khôi phục khi mở máy"** trong tab **Cài Đặt & Hẹn Giờ** để máy tính tự động mở lại mọi thứ mỗi khi bạn bật máy.

---

## 👨‍💻 Tác giả
Phát triển bởi **[trungnguyentn780818-bit](https://github.com/trungnguyentn780818-bit)**.
Mã nguồn mở theo giấy phép MIT.
