"""Offline checks of the /app snapshot hand-off with a fake Modal sandbox."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from harbor.environments.base import ExecResult
from harbor.environments.modal import ModalEnvironment

from px_eval import modal_snapshot as snap


def environment(return_code: int = 0) -> snap.SnapshotModalEnvironment:
    env = snap.SnapshotModalEnvironment.__new__(snap.SnapshotModalEnvironment)
    env._sandbox = MagicMock()
    env._sandbox.snapshot_directory.aio = AsyncMock(return_value=MagicMock(object_id="im-123"))
    env._sandbox.mount_image.aio = AsyncMock()
    env.exec = AsyncMock(return_value=ExecResult(return_code=return_code, stdout="", stderr="tar failed"))
    return env


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "artifacts/app"

    async def test_app_download_writes_only_the_snapshot_id(self):
        env = environment()
        await env.download_dir_with_exclusions(source_dir="/app/", target_dir=self.target, exclude=["**/x y/**"])
        command = env.exec.await_args.args[0]
        self.assertIn("--exclude='**/x y/**' -C /app .", command)
        self.assertIn(f"tar -xf - -C {snap.STAGE}", command)
        env._sandbox.snapshot_directory.aio.assert_awaited_once_with(
            snap.STAGE, timeout=snap.SNAPSHOT_TIMEOUT_SEC, ttl=None)
        self.assertEqual([path.name for path in self.target.iterdir()], [snap.MARKER])
        self.assertEqual(json.loads((self.target / snap.MARKER).read_text())["image_id"], "im-123")

    async def test_failed_stage_raises_before_any_snapshot(self):
        env = environment(return_code=2)
        with self.assertRaisesRegex(RuntimeError, "tar failed"):
            await env.download_dir("/app", self.target)
        env._sandbox.snapshot_directory.aio.assert_not_awaited()

    async def test_other_directories_use_harbor(self):
        env = environment()
        with patch.object(ModalEnvironment, "download_dir", new_callable=AsyncMock) as download, \
                patch.object(ModalEnvironment, "upload_dir", new_callable=AsyncMock) as upload:
            await env.download_dir("/logs/agent", self.target)
            await env.upload_dir(self.target, "/app")
        download.assert_awaited_once_with("/logs/agent", self.target)
        upload.assert_awaited_once_with(self.target, "/app")
        env._sandbox.snapshot_directory.aio.assert_not_awaited()
        env._sandbox.mount_image.aio.assert_not_awaited()

    async def test_upload_with_a_snapshot_id_mounts_it(self):
        self.target.mkdir(parents=True)
        (self.target / snap.MARKER).write_text(json.dumps({"image_id": "im-123"}))
        env = environment()
        with patch.object(snap.modal.Image, "from_id", return_value="image") as from_id:
            await env.upload_dir(self.target, "/app")
        from_id.assert_called_once_with("im-123")
        env._sandbox.mount_image.aio.assert_awaited_once_with("/app", "image")
        env.exec.assert_awaited_once_with("chmod a+rwx /app", user="root")


if __name__ == "__main__":
    unittest.main()
