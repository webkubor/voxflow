"""跨平台落点的自检。

跑：.venv/bin/python tests/test_platform.py

为什么需要它：Windows 分支在这台 Mac 上永远走不到，改坏了也不会有任何
现象 —— 直到某个 Windows 用户装上才发现数据目录在一个资源管理器里看不见
的位置。所以那几条分支得靠注入环境来验，不能靠「在我机器上是好的」。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_data_dir_per_platform():
    """数据根：Windows 走 %LOCALAPPDATA%\\VoxFlow，其余走 ~/.voxflow。"""
    import importlib

    import core.paths as paths

    # 当前平台（Mac/Linux）：必须是 ~/.voxflow，不能因为改动被挪走 ——
    # 已有用户的 8.4 G 模型和作品库都在那儿
    if not paths.IS_WINDOWS:
        assert paths.DATA_DIR == Path.home() / ".voxflow", paths.DATA_DIR

    # 模拟 Windows：LOCALAPPDATA 有值就必须落在它下面
    old_platform, old_local, old_home = sys.platform, os.environ.get("LOCALAPPDATA"), os.environ.get("VOXFLOW_HOME")
    try:
        os.environ.pop("VOXFLOW_HOME", None)
        os.environ["LOCALAPPDATA"] = r"C:\Users\tester\AppData\Local"
        sys.platform = "win32"
        importlib.reload(paths)
        assert paths.IS_WINDOWS, "IS_WINDOWS 没跟着 sys.platform 走"
        assert paths.DATA_DIR == Path(r"C:\Users\tester\AppData\Local") / "VoxFlow", paths.DATA_DIR
    finally:
        sys.platform = old_platform
        if old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_local
        if old_home is not None:
            os.environ["VOXFLOW_HOME"] = old_home
        importlib.reload(paths)
    # 还原后必须回到原样，否则后续测试会拿到污染过的路径
    assert paths.DATA_DIR == Path(os.environ.get("VOXFLOW_HOME") or (Path.home() / ".voxflow"))


def test_voxflow_home_overrides_everything():
    """VOXFLOW_HOME 的优先级最高 —— 测试隔离和外置盘都靠它。"""
    import importlib

    import core.paths as paths

    old = os.environ.get("VOXFLOW_HOME")
    try:
        os.environ["VOXFLOW_HOME"] = "/tmp/vf-test-home"
        importlib.reload(paths)
        assert paths.DATA_DIR == Path("/tmp/vf-test-home"), paths.DATA_DIR
    finally:
        if old is None:
            os.environ.pop("VOXFLOW_HOME", None)
        else:
            os.environ["VOXFLOW_HOME"] = old
        importlib.reload(paths)


def test_model_default_follows_backend():
    """模型名跟后端走：中台认具体名，FreeLLMAPI 认 auto。

    这条挡的是一个真实事故：默认值曾写死 "auto"，对的值 export 在 run.sh 里，
    于是不走 run.sh 的人（Windows、或直接 `voice web`）拿 auto 去打中台就报错。
    """
    from core import llm_client

    assert llm_client.default_model("museav") == "deepseek-v4-flash"
    assert llm_client.default_model("freellm") == "auto"
    # 显式环境变量一律优先
    old = llm_client._env_model
    try:
        llm_client._env_model = "my-model"
        assert llm_client.default_model("museav") == "my-model"
    finally:
        llm_client._env_model = old


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✓ {name}")
    print("\n全部通过")
