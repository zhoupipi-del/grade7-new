// 梨江中学德育管理平台 - 公共脚本
document.addEventListener('DOMContentLoaded', function () {
    // 自动隐藏 flash 消息
    setTimeout(function () {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(function (alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});
