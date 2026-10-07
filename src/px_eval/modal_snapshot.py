"""A Modal environment that moves the /app artifact between sandboxes as a Modal snapshot.

Harbor normally downloads a directory artifact from the agent sandbox to this computer and uploads it
into the verifier sandbox. For /app, this environment keeps the bytes on Modal:

- Agent sandbox: copy /app with the artifact's tar excludes to a stage directory, snapshot the stage, and
  write only the snapshot's Image ID into the host artifact directory.
- Verifier sandbox: when the host artifact directory has an Image ID, mount that Image at /app.

The Image ID file is a normal artifact, so a regrade job copies it and mounts the same snapshot.
Use it with `import_path: px_eval.modal_snapshot:SnapshotModalEnvironment` in the EnvironmentConfig.
"""

import json
import shlex
from pathlib import Path, PurePosixPath

import modal
from harbor.environments.modal import ModalEnvironment

SOURCE = PurePosixPath("/app")
STAGE = "/tmp/px-snapshot"
MARKER = ".px-modal-snapshot.json"
SNAPSHOT_TIMEOUT_SEC = 600


class SnapshotModalEnvironment(ModalEnvironment):
    async def download_dir(self, source_dir: str, target_dir: Path | str):
        if PurePosixPath(source_dir) != SOURCE:
            return await super().download_dir(source_dir, target_dir)
        await self._snapshot(target_dir, exclude=[])

    async def download_dir_with_exclusions(self, *, source_dir: str, target_dir: Path | str, exclude: list[str]):
        if PurePosixPath(source_dir) != SOURCE:
            return await super().download_dir_with_exclusions(
                source_dir=source_dir, target_dir=target_dir, exclude=exclude)
        await self._snapshot(target_dir, exclude=exclude)

    async def upload_dir(self, source_dir: Path | str, target_dir: str):
        marker = Path(source_dir) / MARKER
        if not marker.is_file():
            return await super().upload_dir(source_dir, target_dir)
        image = modal.Image.from_id(json.loads(marker.read_text())["image_id"])
        await self._sandbox.mount_image.aio(target_dir, image)
        # Modal mounts the directory root as root:root 0755; the verifier user may need to write there.
        await self.exec(f"chmod a+rwx {shlex.quote(target_dir)}", user="root")

    async def _snapshot(self, target_dir: Path | str, *, exclude: list[str]) -> None:
        # The same tar excludes as Harbor's download, so the verifier sees the same files.
        flags = " ".join(f"--exclude={shlex.quote(pattern)}" for pattern in exclude)
        result = await self.exec(
            f"set -o pipefail; rm -rf {STAGE} && mkdir -p {STAGE} && tar -cf - {flags} -C {SOURCE} . | tar -xf - -C {STAGE}",
            user="root", timeout_sec=SNAPSHOT_TIMEOUT_SEC,
        )
        if result.return_code != 0:
            raise RuntimeError(f"could not stage {SOURCE} for a snapshot: {result.stderr or result.stdout}")
        image = await self._sandbox.snapshot_directory.aio(STAGE, timeout=SNAPSHOT_TIMEOUT_SEC, ttl=None)
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        (Path(target_dir) / MARKER).write_text(json.dumps({"image_id": image.object_id, "source": str(SOURCE)}))
