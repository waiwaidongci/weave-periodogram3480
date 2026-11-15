QR_RANK_TOL=1e-10
POWER_TIE_TOL=1e-12
ALGORITHM_VERSION='centered-coordinate-qr-global-max-v1'
# 测线规模与分批导入上限
MIN_POINTS=4
MAX_POINTS=100_000
MAX_BATCH_POINTS=10_000
MAX_SPAN_MM=10_000
# 全量QR缓存（2*F*N*8字节）低于该字节数时走原算法，保证小样本逐位一致；
# 超过则切换分块流式引擎，结果结构与确定性不变。
LEGACY_CACHE_BYTE_LIMIT=64*1024*1024
# 流式引擎分块：频点块与置换块，按峰值内存≤256MiB设计（十万点实测全路径<230MiB）
FREQ_BLOCK=24
PERM_BLOCK=8
# 单次分析峰值内存红线（MiB），worker自检用
ANALYSIS_MEMORY_LIMIT_MIB=256
