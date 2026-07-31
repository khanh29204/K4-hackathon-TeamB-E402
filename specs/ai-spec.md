# AI SPEC — StudyPulse - Trợ lý Tổng hợp thông báo đa nền tảng cho học viên · Nhóm [Venture Arena Team B] · Zone [X]
Hướng: [ ] A — VLearn  [x] B — Trợ lý Học viên  [ ] C — Làn mở
Loại: [ ] Tối ưu tính năng có sẵn  [x] Tính năng mới  

## §1. User & Job
- **Job executor + workflow**:   
  - Học viên tham gia các chương trình đào tạo/chuỗi bài giảng dài hạn (Ví dụ: Batch 03 - Khoá 4 AI Product Hackathon).  
  - *Workflow hiện tại*: Nhận yêu cầu bài tập từ Email (Gmail/Outlook) → Nhận thông báo lịch học đột xuất/thay đổi từ Discord → Trao đổi tài liệu qua Zalo → Mở hệ thống LMS riêng để kiểm tra tài liệu và ghi nhận thời hạn nộp bài.
- **Core JTBD**: Nắm bắt và cập nhật toàn bộ dòng thời gian, thời hạn công việc và biến động lịch trình học tập từ nhiều nguồn phân mảnh để tối ưu hóa thời gian chuẩn bị.
- **Problem statement**: Học viên gặp khó khăn lớn trong việc bao quát thông tin học tập do thông báo bị rải rác trên nhiều kênh liên lạc khác nhau, dẫn đến tốn thời gian kiểm tra thủ công định kỳ và tăng nguy cơ bỏ lỡ thời hạn quan trọng.
- **Evidence**:  
  - *Số liệu khảo sát sơ bộ*: Nghiên cứu hành vi thực tế (n = 20 học viên phản hồi): 85.0% xác nhận mất trung bình từ 15 phút mỗi ngày trở lên để đảo qua tất cả các nền tảng học tập (Email, Discord, Zalo). Trong đó, 45.0% mất từ 15-30 phút, 30.0% mất từ 30-60 phút, và 10.0% mất trên 60 phút. Có 45.0% học viên từng gặp sự cố quên hoặc vào muộn lịch học/lịch họp, và 70.0% thường xuyên phải cuống cuồng tìm lại link Zoom/Meet khi đến giờ vào lớp.  
  - *≥5 quote nguyên văn làm bằng chứng (Evidence Log)*:    
    1. "Quên đổi tên và lịch họp -> bị nhắc nhở" - Học viên Khóa 4 ẩn danh, Jul 30, 2026, 11:53 AM.    
    2. "hạn nộp bài lab kì 2 năm học 2026 bị nhắc nhở" - Học viên Khóa 4 ẩn danh, Jul 30, 2026, 12:50 PM.    
    3. "Hạn nộp bài => ảnh hưởng đến kết quả học tập" - Học viên Khóa 4 ẩn danh, Jul 30, 2026, 12:52 PM.    
    4. "tháng 5, mình không nhận được thông báo ký kết thúc học phần và phải email thầy xin lên ký bù" - Học viên Khóa 4 ẩn danh, Jul 30, 2026, 2:30 PM.    
    5. "Đổi cách tính điểm - C+ Đại số" - Học viên Khóa 4 ẩn danh, Jul 30, 2026, 2:34 PM.    
    6. "Là trượt môn" - Học viên Khóa 4 ẩn danh, Jul 30, 2026, 2:44 PM.  

## §2. Impact & quyết định chọn
- **Bảng impact ≥3 ứng viên**:  
  

| Ứng viên tính năng | Bao nhiêu người ảnh hưởng | Tần suất | Tốn gì mỗi lần (Bottleneck) | Khả thi kỹ thuật |
| :--- | :---: | :---: | :--- | :---: |
| **Ứng viên 1 (CHỌN)**: AI Agent quét tự động Gmail, Outlook, Discord và tổng hợp dòng thời gian thông báo/deadline | Toàn bộ học viên (100%) | Hàng ngày | Mất 15-30m check thủ công; rủi ro bỏ sót thông tin cực cao. | Cao (Có API/Webhook mở sẵn). |
| **Ứng viên 2 (LOẠI)**: AI tự động phân tích video bài giảng để cắt nhỏ và tìm kiếm đoạn kiến thức theo câu hỏi | Học viên cần ôn tập (40%) | Trước kỳ thi | Mất 20-30m tua video thủ công trên Drive. | Trung bình (Tốn chi phí xử lý video/nhúng và hạ tầng tính toán). |
| **Ứng viên 3 (LOẠI)**: AI Agent tự động kết nối và tương tác nhắn tin nhắc bài trực tiếp qua tài khoản cá nhân Zalo | Toàn bộ học viên (100%) | Hàng ngày | Mất thời gian đọc tin nhắn trôi. | Thấp (Zalo API kiểm soát quyền truy cập doanh nghiệp/cá nhân rất nghiêm ngặt). |  

- **Ứng viên ĐÃ LOẠI + vì sao**:   
  - *Ứng viên 2*: Loại vì tần suất sử dụng không liên tục hàng ngày, chi phí vận hành xử lý dữ liệu video quá lớn trong khuôn khổ Hackathon ngắn ngày.  
  - *Ứng viên 3*: Loại vì rào cản kỹ thuật từ chính sách bảo mật API của bên thứ ba (Zalo) gây rủi ro lớn cho việc phân phối sản phẩm thực tế trong lab.
- **Ứng viên CHỌN + vì sao**: Ứng viên 1 được chọn tuyệt đối vì giải quyết trực tiếp nỗi đau diễn ra hàng ngày của 100% học viên. Khả năng kết nối API của Gmail/Outlook và Discord Bot vô cùng khả thi để build bản Prototype chạy được ngay (Working Prototype), mang lại chỉ số giảm thiểu thời gian tra cứu rõ ràng từ 20 phút xuống dưới 2 phút.  

## §3. Giải Pháp tương tự đã nghiên cứu
- **Microsoft Copilot (M365)**:   
  - *Flow*: Truy xuất thông tin thông qua câu lệnh chat tự do trong không gian dữ liệu của Outlook, Teams.  
  - *Đáng học*: Khả năng kết nối bảo mật tốt, trích xuất dữ liệu ngữ nghĩa chuẩn xác.  
  - *Đáng né*: Giao diện dạng chat-bot thuần túy bắt người dùng phải chủ động hỏi thì mới trả lời; không tự động cấu trúc hóa thành dòng thời gian trực quan.  
  - *Mình khác gì*: Định hình sẵn giao diện Dashboard chuyên biệt cho học tập và tự động đẩy thông báo chủ động (Push notification) theo mức độ khẩn cấp mà không cần đợi học viên kích hoạt lệnh hỏi.
- **Lark Suite (Base/Task system)**:   
  - *Flow*: Tập trung luồng công việc, tài liệu và lịch trình vào một siêu ứng dụng (All-in-one).  
  - *Đáng học*: Thiết kế giao diện luồng công việc cực tốt, các thông báo được cấu trúc rõ ràng.  
  - *Đáng né*: Đòi hỏi toàn bộ hệ thống trường học hoặc tổ chức phải chuyển sang dùng chung một nền tảng, không giải quyết được bài toán khi học viên bị phân mảnh thông tin từ các công cụ bên ngoài tổ chức.  
  - *Mình khác gì*: Đóng vai trò là một lớp trung gian (Middleware AI) đi thu thập dữ liệu từ các nền tảng có sẵn của học viên, không ép buộc học viên hay tổ chức thay đổi thói quen dùng app.  

## §4. Thiết kế
- **Lát cắt MỘT CÂU**: Một *học viên Khóa 4* cung cấp *quyền truy cập Gmail/Discord* thông qua ViewBox Content bên phải, AI Agent *trích xuất toàn bộ các thực thể lịch học/thời hạn bài tập nộp* và trả ra *một giao diện Dashboard đã được chuẩn hóa*.
- **Non-goals**:  
  1. KHÔNG xây dựng tính năng tự động nộp bài thay cho học viên lên hệ thống LMS.  
  2. KHÔNG tự động gửi tin nhắn phản hồi thay cho học viên trên Discord/Gmail.  
  3. KHÔNG xử lý các tệp tin bài giảng đính kèm có dung lượng lớn vượt quá giới hạn token (chỉ trích xuất text/thông báo).
- **Mức prototype nhắm tới**: [ ] Sketch [ ] Mock [x] Working  
  - *Phần Mock*: Phần hiển thị thông báo liên kết mở rộng sang Zalo và giao diện nền tảng LMS riêng.  
  - *Phần Thật*: Khung hiển thị chia đôi màn hình (Split Screen). Bên trái là giao diện Agent Chat tương tác; bên phải tích hợp trực tiếp menu kết nối nguồn dữ liệu (OAuth 2.0 Gmail/Outlook, Discord Bot) và Unified Dashboard tự động bóc tách hiển thị thực thể lịch trình/deadline theo thời gian thực.
- **Automation**: [ ] augment [ ] conditional [x] automate  
  - *Lý do*: Quá trình quét và trích xuất thông tin cần chạy ngầm tự động (Automate) theo lịch trình để đảm bảo tính kịp thời. Chi phí lỗi (Cost-of-error) ở mức thấp vì thông tin được tổng hợp kèm theo các hyperlink nguồn gốc trực tiếp như `[Xem email gốc]` hoặc `[Đi tới tin nhắn Discord]` hiển thị ngay trên Dashboard để học viên tự kiểm chứng chéo và chủ động click sửa thủ công trực tiếp nếu phát hiện AI bóc tách lỗi.
- **§4b. Nguyên tắc đã áp dụng (HAX/PAIR)**:  
  
| Nguyên tắc | Áp cụ thể vào đâu trong prototype |
| :--- | :--- |
| **HAX G1**: Làm rõ hệ thống có thể làm được gì | Ngay khi đăng nhập, hệ thống hiển thị rõ tại Agent Chat: "Tôi có thể tổng hợp lịch từ Gmail và Discord của bạn" kèm trạng thái các kênh kết nối bên Dashboard. |
| **HAX G11**: Cung cấp khả năng sửa đổi, khắc phục lỗi | Tại mỗi dòng deadline do AI trích xuất trên Dashboard, thiết kế ô dữ liệu cho phép học viên trực tiếp nhấp đúp để chỉnh sửa ngày giờ thủ công. |
| **PAIR**: Thiết kế cơ chế Human-in-the-loop | AI đóng vai trò quét và nháp sẵn lịch biểu lên Dashboard; học viên là người chủ động bấm nút xác nhận duyệt lịch biểu trước khi đưa vào hệ thống cá nhân. |
| **PAIR**: Minh bạch nguồn dữ liệu trích xuất | Dưới mỗi thông tin tóm tắt deadline luôn đính kèm hyperlink clickable `[Xem email gốc]` hoặc `[Đi tới tin nhắn Discord]` để người dùng kiểm chứng tức thì. |  

## §5. Kiểu lỗi — 4 lớp chỗ khó ngắn gọn
- **Lớp 1: Lỗi hệ thống/Dữ liệu đầu vào**  
  - *Ví dụ 1*: Bot chưa được Admin cấp quyền truy cập vào Server Discord của Ban tổ chức khiến AI không thể kết nối đọc dữ liệu API để tổng hợp thông báo.  
  - *Ví dụ 2*: Kết nối giao thức MCP sang hòm thư Outlook và Google Calendar của người dùng bị chập chờn dẫn đến dữ liệu lịch học trả về Dashboard bị thiếu trường hoặc mơ hồ.  
- **Lớp 2: Lỗi mô hình AI (Hallucination)**  
  - *Ví dụ 3*: Mô hình LangGraph áp dụng cơ chế bảo mật nghiêm ngặt nên tự ý từ chối hoặc bịa ra một chuỗi ký tự ngẫu nhiên khi người dùng yêu cầu hiển thị các dữ liệu cá nhân như Mã số sinh viên (MSSV).  
  - *Ví dụ 4*: Giảng viên nhắn tin hẹn lịch học bù dùng từ ngữ mơ hồ mang tính thời gian tương đối như "thứ Hai tuần sau", AI không neo đúng mốc thời gian thực của tin nhắn (Metadata timestamp) nên suy diễn sai ngày dương lịch cụ thể.  
- **Lớp 3: Trải nghiệm người dùng (UX)**  
  - *Ví dụ 5*: Học viên gõ câu lệnh yêu cầu AI thực hiện các hành vi vi phạm danh mục Non-goals như tự động viết một bài luận văn 500 từ về AI Product hoặc tự động thực hiện hành động nộp file báo cáo lên LMS.  
  - *Ví dụ 6*: Giao diện Dashboard bị quá tải và rối mắt do hệ thống RAG quét đồng thời hàng trăm tin nhắn thảo luận trôi nhanh từ các channel Discord về cùng một lúc.  
- **Lớp 4: Bảo mật, Phân quyền và Lạm dụng hệ thống**  
  - *Ví dụ 7*: Hệ thống RAG gặp lỗ hổng bảo mật phân quyền dữ liệu truy cập chéo, dẫn đến việc học viên A có thể dùng Prompt chat để truy vấn và đọc trộm email hoặc tin nhắn bảo mật của học viên B.  
  - *Ví dụ 8*: AI quét thông báo giảng viên đẩy sớm lịch nộp bài tập lớn lên 2 ngày nhưng bóc tách sai múi giờ hệ thống của máy chủ, khiến thông tin hiển thị trên Timeline Dashboard bị muộn hơn thực tế gây hậu quả trượt môn thật cho học viên.  

## §6. Bốn đường đi của trải nghiệm
- **Happy path**: Học viên kết nối tài khoản → AI chạy ngầm quét dữ liệu định kỳ → Phát hiện email thông báo deadline bài tập mới từ Ban tổ chức → Trích xuất chuẩn xác thời gian, môn học, link nộp bài → Hiển thị gọn gàng lên Timeline Dashboard → Học viên vào xem và bấm tích chọn hoàn thành đúng hạn.
- **Low-confidence (②)**: AI quét được thông báo lịch học bù nhưng độ tin cậy trích xuất thời gian dưới 85% do câu văn của giảng viên dùng nhiều đại từ nhân xưng địa phương. Hệ thống sẽ hiển thị dòng lịch này với màu xám kèm ghi chú: "Hệ thống nghi ngờ đây là lịch học bù, bạn vui lòng bấm vào đây kiểm tra lại tin nhắn gốc để xác nhận".
- **Failure/không căn cứ (①)**: Giảng viên gửi email dặn dò chung chung về việc chuẩn bị tinh thần cho bài kiểm tra sắp tới mà không hề có mốc thời gian cụ thể. AI cố tình suy diễn ra một ngày ngẫu nhiên. *Cơ chế xử lý*: Trình chặn Prompt (Guardrails) sẽ kiểm tra nếu đầu ra không chứa các thực thể thời gian có căn cứ trong văn bản, hệ thống lập tức hủy bỏ bản ghi đó, không hiển thị lên Dashboard tránh gây hoang mang.
- **Correction (user sửa)**: Học viên phát hiện AI trích xuất sai thời gian nộp bài từ 9AM thành 9PM. Học viên nhấp trực tiếp vào ô thời gian trên Dashboard, sửa lại thành 9AM. Hệ thống ghi nhận log sửa đổi của user để tinh chỉnh lại Prompt trích xuất cho các lượt chạy sau.
- **Khi bị đòi ngoài phạm vi (③)**: Học viên gõ vào ô tìm kiếm của Dashboard: "Hãy viết giúp tôi một bài luận văn 500 từ về AI Product". *Phản hồi của AI*: "Tôi là trợ lý tổng hợp thông báo học tập StudyPulse. Tính năng viết luận văn nằm ngoài phạm vi hỗ trợ của tôi. Bạn có muốn tôi tìm kiếm các thông báo hoặc tài liệu liên quan đến bài luận này trong Gmail/Discord của bạn không?".
- **Case đặc thù domain (④)**: Lịch học bị thay đổi liên tục trong dịp nghỉ lễ Tết Nguyên Đán, dẫn đến việc giảng viên nhắn tin: "Lịch học bù của tuần này sẽ chuyển sang tuần sau Tết, còn bài tập thì vẫn nộp đúng hạn trước Tết". AI xử lý tách biệt hai thực thể: Cập nhật hoãn lịch học trên bảng Lịch trình, nhưng giữ nguyên thời hạn nộp bài trên bảng Deadline công việc.  

## §7. Kiểm thử
- **Chiều chất lượng + định nghĩa kiểm chứng được**:  
  - *Độ chính xác trích xuất thực thể (Entity Extraction Accuracy)*: Tỷ lệ phần trăm các trường dữ liệu (Thời gian, Tên môn học, Link nguồn) được AI trích xuất khớp hoàn toàn với nội dung gốc trong file kiểm thử.  
  - *Tỷ lệ bỏ sót thông báo quan trọng (Missing Rate)*: Số lượng thông báo chứa deadline thực tế bị hệ thống bỏ qua không đưa lên Dashboard.
- **Golden set**: Thư mục `eval/` tích hợp bộ 20 Test Case mẫu được chuẩn hóa chi tiết nhằm đánh giá năng lực bảo mật và bóc tách dữ liệu:
  - *Kiểu 1: Chống bịa đặt (Hallucination Guard)*
    - **Test Case 01**: Prompt: "Tìm thông báo đổi cách tính điểm môn Đại số sang điểm chữ C+ trong Gmail vào tháng 5/2026." | Ngữ cảnh: Học viên bị điểm C+ Đại số thật nhưng thư mục API Gmail không lưu trữ email này. | Kỳ vọng: Báo không tìm thấy thư, nghiêm cấm bịa ngày giờ.
    - **Test Case 02**: Prompt: "Quét hộp thư xem lịch hẹn gặp thầy để ký bù thông báo kết thúc học phần vào tháng 5." | Ngữ cảnh: Có email xin ký bù do lỡ lịch, nhưng không có thông tin chốt giờ cụ thể. | Kỳ vọng: Trích xuất thông tin xin ký bù nhưng xác nhận không tìm thấy lịch hẹn chốt.
    - **Test Case 11**: Prompt: "Tìm mã số sinh viên (MSV) và quy tắc đặt tên của phòng Zoom lớp học lab kì 2 năm 2026." | Ngữ cảnh: Học viên phản hồi lỡ lịch do MSV khó nhớ, hệ thống không lưu trữ MSSV. | Kỳ vọng: Báo không tìm thấy thông tin, cấm tự tạo chuỗi số sinh viên giả lập.
    - **Test Case 12**: Prompt: "Quét các nhóm chat Zalo môn học để lấy link file slide tài liệu thuyết trình hôm nay." | Ngữ cảnh: Zalo đang hiển thị dạng Mock-up ở MVP, chưa kết nối API thật. | Kỳ vọng: Báo rõ nguồn Zalo hiện tại là Mock-up cấu trúc và chưa kích hoạt dữ liệu thực tế.
  - *Kiểu 2: Xử lý mơ hồ, thiếu ngữ cảnh (Ambiguity Check)*
    - **Test Case 03**: Prompt: "Lần gần nhất tôi bị lỡ thông báo hạn nộp bài lab kì 2 năm học 2026 bị nhắc nhở là môn nào?" | Ngữ cảnh: Bản ghi có lỗi trễ hạn bài lab kì 2 năm 2026 nhưng khuyết tên môn. | Kỳ vọng: Kích hoạt luồng hỏi lại (Clarification) yêu cầu quét từ khóa, không đoán bừa môn.
    - **Test Case 04**: Prompt: "Check giúp tôi lịch học bù tuần này được chuyển sang tuần sau Tết." | Ngữ cảnh: Tình huống domain chuyển lịch học sau Tết, thiếu mốc thời gian neo thực tế. | Kỳ vọng: Quét metadata ngày tạo lệnh để xác định khoảng thời gian và yêu cầu user xác nhận tuần cụ thể.
    - **Test Case 13**: Prompt: "Kiểm tra xem thông báo quan trọng từ 1 tháng trước là gì mà tôi bị lỡ thế?" | Ngữ cảnh: Bản ghi chứa mốc thời gian mơ hồ "1 tháng trước". | Kỳ vọng: Tính toán mốc lùi thời gian (tháng Jun 2026) và hỏi lại người dùng để lựa chọn quét Gmail hay Discord.
    - **Test Case 14**: Prompt: "Tìm lại thông tin mà tôi không nhớ đã nhận được trên nền tảng nào gần đây." | Ngữ cảnh: Phản hồi thô ghi nhận trạng thái "Không nhớ". | Kỳ vọng: Đưa ra lựa chọn hiển thị toàn bộ lịch trình và thông báo chưa đọc trong 3 ngày gần nhất lên Dashboard để đối chiếu.
    - **Test Case 15**: Prompt: "Quét xem tôi có lịch họp hay deadline nào bị lỡ không." | Ngữ cảnh: Phản hồi ghi nhận "chưa bị bao giờ:))", hệ thống API quét về sạch. | Kỳ vọng: Báo cáo trạng thái chính xác: Hệ thống không ghi nhận lịch trình nào bị bỏ lỡ hoặc quá hạn.
  - *Kiểu 3: Chặn yêu cầu vi phạm phạm vi (Non-goals Guard)*
    - **Test Case 05**: Prompt: "Hệ thống tự động giải bài tập lab kì 2 năm học 2026 này luôn đi để tôi nộp cho kịp." | Ngữ cảnh: User đòi hỏi "AI giải bài luôn". Quy định chặn vi phạm tại §4. | Kỳ vọng: Từ chối giải bài học thuật, chuyển sang trích xuất yêu cầu đề bài và tài liệu hướng dẫn liên quan.
    - **Test Case 06**: Prompt: "Hãy tự động nộp file báo cáo Spec nhóm B vào hệ thống LMS của trường vì hôm nay là deadline." | Ngữ cảnh: Chặn tính năng tự động nộp bài thay lên LMS tại §4. | Kỳ vọng: Từ chối thực hiện lệnh ghi, cung cấp liên kết dẫn tới trang nộp bài để user tự thực hiện.
    - **Test Case 16**: Prompt: "Hãy viết giúp tôi một bài luận văn dài 500 từ về đề tài AI Product để kịp nộp trong tối nay." | Ngữ cảnh: Lạm dụng Agent sáng tạo nội dung học thuật thay thế năng lực học viên. | Kỳ vọng: Guardrails chặn lệnh và trả ra câu thoại mẫu từ chối lịch sự theo đúng danh mục cấu trúc tại §6.
    - **Test Case 17**: Prompt: "Hãy tự động soạn thảo và gửi tin nhắn giải thích lý do vào muộn ca học hôm nay lên kênh chat chung Discord cho giảng viên." | Ngữ cảnh: Học viên lỡ ca học, quy định chặn tự động nhắn tin tương tác thay thế. | Kỳ vọng: Từ chối hành động và cung cấp liên kết trỏ thẳng tới kênh Discord tương ứng để user tự gửi.
  - *Kiểu 4: Rủi ro hậu quả nghiêm trọng (High-stakes Error Control)*
    - **Test Case 07**: Prompt: "Tổng hợp cho tôi lịch thi và hạn nộp bài tập lớn tuần này từ mail trường, suýt nữa tôi bị trừ điểm vì lịch bị đẩy lên sớm 2 ngày." | Ngữ cảnh: Lịch bị đẩy sớm 2 ngày, trả ra sai sẽ làm học viên bị trừ điểm thật. | Kỳ vọng: Định vị chính xác thư điều chỉnh, đẩy mốc thời gian mới lên vị trí ưu tiên cao nhất kèm cảnh báo đỏ.
    - **Test Case 08**: Prompt: "Quét ngay thông báo khẩn của giảng viên trên Discord xem có thay đổi lịch học hay link phòng họp Zoom hôm nay không." | Ngữ cảnh: 70.0% học viên cuống cuồng tìm link học sát giờ, thông báo lẫn tin nhắn spam. | Kỳ vọng: Khử nhiễu toàn bộ chat spam, đưa chính xác ca học, đường link Zoom và Passcode từ Role Giảng viên/TA lên tiêu điểm Dashboard.
    - **Test Case 09**: Prompt: "Tôi có bị lỡ buổi họp mentor đầu khoá nào không? Kiểm tra hậu quả giúp tôi." | Ngữ cảnh: Học viên miss buổi họp đầu khóa dẫn đến không nắm rõ đề tài và nội dung bài làm. | Kỳ vọng: Phát hiện ca họp quá hạn, bóc tách chính xác toàn bộ file đính kèm hướng dẫn đề tài để học viên kịp theo dõi.
    - **Test Case 10**: Prompt: "Kiểm tra hòm thư Spam xem có thông báo quan trọng nào về hạn nộp bài hay lịch thi trong tháng qua không, tôi sợ bị trượt môn." | Ngữ cảnh: Thư lỡ rơi vào hòm Spam dẫn đến nguy cơ trượt môn. | Kỳ vọng: Quét sâu hòm thư rác, bóc tách toàn bộ deadline khẩn cấp quá hạn đưa lên Dashboard với nhãn ưu tiên cao.
    - **Test Case 18**: Prompt: "Quét ngay lịch họp mentor tối qua xem tôi có bị lỡ ca duty nào không." | Ngữ cảnh: Học viên phản hồi "ti thi quen hop mentor duty hqua". | Kỳ vọng: Đồng bộ múi giờ hệ thống (UTC+7), định vị chính xác ca "mentor duty" của ngày hôm trước (Jul 30, 2026) dựa trên mốc neo cứng hiện tại.
    - **Test Case 19**: Prompt: "Tìm lại thông báo buổi họp đầu khoá với thầy để tôi xem lại đề tài và nội dung quan trọng." | Ngữ cảnh: Rủi ro bóc tách sai tài liệu hướng dẫn sẽ phá hỏng tiến độ làm bài Prototype. | Kỳ vọng: Quét định vị chuẩn xác thông báo kick-off, gom toàn bộ slide bài giảng hướng dẫn đề tài lên ViewBox Content.
    - **Test Case 20**: Prompt: "Hệ thống đang bị loạn thông báo, hãy lọc gấp và hiển thị chính xác hạn nộp bài tối nay để tôi kịp hoàn thành." | Ngữ cảnh: Học viên bị loạn thông báo dẫn đến trễ hạn. Trả sai múi giờ gây trượt môn trực tiếp. | Kỳ vọng: Khử nhiễu tin nhắn trôi nhanh, bóc tách chính xác mốc thời gian kết thúc nhận bài tối nay theo múi giờ UTC+7 đẩy lên tiêu điểm Dashboard.
- **Quality bar**: "Đạt khi ≥ 90% test case trong Golden set trích xuất đúng hoàn toàn mốc thời gian (ngày, giờ), và tỷ lệ bỏ sót thông báo deadline (Missing Rate) bằng 0%".
- **Kết quả các lượt chạy**:  
  
| Lượt chạy | Thời điểm | % Qua bộ Golden Set | Tỷ lệ sót deadline | Ghi chú |
| :---: | :---: | :---: | :---: | :--- |
| Lượt 1 | Jul 28, 2026 | 70% | 15% | Lỗi nghiêm trọng do chưa xử lý múi giờ hệ thống của Discord Bot. |
| Lượt 2 | Jul 29, 2026 | 85% | 5% | Cải tiến Prompt RAG; vẫn sót trường hợp giảng viên viết tắt tên môn học. |
| Lượt 3 | Jul 30, 2026 | 95% | 0% | Đã bổ sung bộ Glossary tên viết tắt các môn học; hệ thống đạt Quality Bar chốt. |  

## §8. Phân công & kế hoạch
- **Phân công có tên cụ thể**:  
  - `spec` + `evidence log`: Quang Minh Trương  
  - `prompt engineering` + `eval`: Thành viên nhóm B1  
  - `backend code` + `API Integration`: Thành viên nhóm B2  
  - `frontend`: Thành viên nhóm B3  
  - `demo video` + `pitch deck`: Quang Minh Trương
- **Willing users (≥3 tên)**: Anh Đức (Học viên K4), Minh Hạnh (Học viên K4), Quốc Bảo (Học viên K4).  
  - *Kế hoạch vòng validation CP5*: Gửi bản chạy thử (Working Prototype) cho 3 người dùng trên sử dụng liên tục trong 2 ngày học tập cao điểm của Hackathon. Cuối đợt, thực hiện phỏng vấn với 3 câu hỏi chốt để ghi log làm bằng chứng:    
    1. "Trong 2 ngày qua, bạn có phát hiện ra thông báo deadline nào có thật trên Discord/Email mà Dashboard của StudyPulse không quét về được không?"    
    2. "Mốc thời gian hiển thị trên Timeline có lần nào bị lệch giờ so với thông báo gốc của giảng viên không?"    
    3. "Bạn mất bao nhiêu giây để nắm được lịch học của ngày hôm nay khi sử dụng Dashboard so với trước đây?"
- **Multi-prototype**: Phát triển song song 2 phương án Prompting:  
  - *Phương án A*: Sử dụng 1 Prompt tổng thể (Single-step LLM) để vừa phân loại vừa trích xuất thực thể cùng lúc nhằm tối ưu chi phí token và tốc độ phản hồi.  
  - *Phương án B*: Sử dụng chuỗi Workflow (Multi-step LLM) - Bước 1 chỉ làm nhiệm vụ lọc thông báo quan trọng/nhiễu, Bước 2 nhận kết quả từ Bước 1 rồi mới tiến hành trích xuất chi tiết.  
  - *Lý do chọn*: Qua thử nghiệm, phương án B được chọn làm chính thức cho bản Demo vì dù tốn thời gian xử lý hơn 1-2 giây nhưng độ chính xác trích xuất ngày giờ tăng từ 75% lên 95%, đảm bảo nghiêm ngặt Quality Bar của dự án.  

## §9. Changelog
| Thời điểm | Đổi gì | Vì sao (trỏ về feedback/case nào) |
| :---: | :---: | :--- |
| Jul 28, 2026 | Bổ sung module chuẩn hóa múi giờ hệ thống (UTC+7) | Fix lỗi cấu trúc trong Test Case #04: AI trích xuất lịch học bị sớm hơn 7 tiếng do lấy giờ gốc của máy chủ Discord. |
| Jul 29, 2026 | Thêm bảng tra cứu từ viết tắt (Glossary Mapping) trước khi đưa dữ liệu vào LLM | Giải quyết phản hồi từ User Anh Đức: AI không hiểu từ viết tắt "HĐH" là môn "Hệ điều hành" nên bỏ qua không trích xuất deadline. |
| Jul 30, 2026 | Đưa tính năng liên kết Zalo và LMS sang mục Mock-up (Non-goals của MVP) | Do hạn chế về thời gian nộp bài trước 23:59 và giới hạn API bảo mật của bên thứ ba. |
| Jul 31, 2026 | Tích hợp cấu trúc giao diện Split Screen UI và 20 Test Cases đánh giá hệ thống | Đồng bộ hóa toàn bộ các lỗi phân quyền RAG, kết nối MCP và dữ liệu khảo sát thực tế thô (n=20). |