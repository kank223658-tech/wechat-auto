module.exports = {
    publicPath: './',
    chainWebpack: config => {
        // G 盘是 FAT32（无 ACL），public/images/OfficialAccount 目录元数据损坏，
        // 枚举时报 EPERM scandir 导致编译失败 → copy 阶段跳过该目录。
        // 目录修复（管理员运行 chkdsk G: /f）后可删除本段。
        config.plugin('copy').tap(args => {
            const opts = args[0][0] || (args[0][0] = {});
            opts.ignore = (opts.ignore || []).concat([
                'images/OfficialAccount',
                'images/OfficialAccount/**'
            ]);
            return args;
        });
    }
}
