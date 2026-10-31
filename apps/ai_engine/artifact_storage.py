"""Cloudflare R2 storage and integrity verification for AI model artifacts.

Artifacts are never unpickled until their SHA-256 and HMAC signatures have
been verified against the trusted metadata stored alongside the object.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.metadata
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _settings() -> tuple[Any, str, str]:
    account = os.environ.get("CLOUDFLARE_R2_ACCOUNT_ID", "").strip()
    access = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("CLOUDFLARE_R2_BUCKET", "").strip()
    signing_key = os.environ.get("AI_MODEL_SIGNING_KEY", "")
    if not all((account, access, secret, bucket, signing_key)):
        raise RuntimeError("Cloudflare R2 and AI_MODEL_SIGNING_KEY must be configured before model artifacts can be stored or loaded")
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for Cloudflare R2 model storage") from exc
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="auto",
    )
    return client, bucket, signing_key


def package_versions() -> dict[str, str]:
    packages = ("numpy", "pandas", "scikit-learn", "joblib", "xgboost", "lightgbm")
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def schema_document(feature_names: list[str] | tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "features": [{"name": str(name), "dtype": "float64", "position": index} for index, name in enumerate(feature_names)],
        "feature_names": [str(name) for name in feature_names],
        "input_dtype": "float64",
        "input_shape": [None, len(feature_names)],
    }


def _signature(payload: bytes, signing_key: str) -> tuple[str, str]:
    digest = hashlib.sha256(payload).hexdigest()
    mac = hmac.new(signing_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return digest, mac


def upload_model_artifacts(local_path: str | Path, metadata: dict[str, Any], object_stem: str) -> dict[str, str]:
    client, bucket, signing_key = _settings()
    payload = Path(local_path).read_bytes()
    digest, mac = _signature(payload, signing_key)
    prefix = os.environ.get("AI_MODEL_PREFIX", "algobot/models").strip("/")
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", object_stem)
    key = f"{prefix}/{safe_stem}.joblib"
    sidecar_key = f"{key}.json"
    envelope = {
        "artifact_key": key,
        "sha256": digest,
        "hmac_sha256": mac,
        "feature_schema": metadata.get("feature_schema", {}),
        "feature_schema_sha256": hashlib.sha256(
            json.dumps(metadata.get("feature_schema", {}), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "packages": package_versions(),
        "model_metadata": metadata,
    }
    manifest_bytes = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    envelope["manifest_hmac_sha256"] = hmac.new(
        signing_key.encode("utf-8"), manifest_bytes, hashlib.sha256
    ).hexdigest()
    client.put_object(
        Bucket=bucket, Key=key, Body=payload,
        ContentType="application/octet-stream",
        Metadata={"sha256": digest, "hmac-sha256": mac, "schema-sha256": envelope["feature_schema_sha256"]},
    )
    client.put_object(
        Bucket=bucket, Key=sidecar_key,
        Body=json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json",
    )
    return {"artifact": f"r2://{bucket}/{key}", "artifact_metadata": f"r2://{bucket}/{sidecar_key}", "sha256": digest, "hmac_sha256": mac, "feature_schema_sha256": envelope["feature_schema_sha256"]}


def download_verified_artifact(uri: str, expected_features: list[str] | tuple[str, ...]) -> str:
    parsed = urlparse(str(uri))
    if parsed.scheme != "r2" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Model artifact reference is not a valid r2://bucket/key URI")
    client, configured_bucket, signing_key = _settings()
    bucket = parsed.netloc
    if bucket != configured_bucket:
        raise ValueError("Model artifact bucket does not match the configured trusted bucket")
    key = parsed.path.lstrip("/")
    sidecar_key = f"{key}.json"
    sidecar = json.loads(client.get_object(Bucket=bucket, Key=sidecar_key)["Body"].read())
    supplied_manifest_mac = str(sidecar.pop("manifest_hmac_sha256", ""))
    manifest_bytes = json.dumps(sidecar, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected_manifest_mac = hmac.new(
        signing_key.encode("utf-8"), manifest_bytes, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_manifest_mac, expected_manifest_mac):
        raise ValueError("Model artifact metadata manifest HMAC verification failed")
    expected_schema = schema_document(expected_features)
    expected_schema_hash = hashlib.sha256(
        json.dumps(expected_schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    actual_schema_hash = hashlib.sha256(
        json.dumps(sidecar.get("feature_schema", {}), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(expected_schema_hash, actual_schema_hash):
        raise ValueError("Model feature schema does not match the live inference feature contract")
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    digest, mac = _signature(body, signing_key)
    if not hmac.compare_digest(digest, str(sidecar.get("sha256", ""))):
        raise ValueError("Model artifact SHA-256 verification failed")
    if not hmac.compare_digest(mac, str(sidecar.get("hmac_sha256", ""))):
        raise ValueError("Model artifact HMAC verification failed")
    # Version drift is a hard error: loading an unpickled estimator with an
    # incompatible sklearn/XGBoost/LightGBM runtime is not safe or reproducible.
    installed = package_versions()
    recorded = sidecar.get("packages", {})
    for package in ("scikit-learn", "joblib", "xgboost", "lightgbm"):
        if recorded.get(package) not in (None, "not-installed") and installed.get(package) != recorded.get(package):
            raise RuntimeError(f"Model dependency mismatch for {package}: trained={recorded[package]}, runtime={installed.get(package)}")
    handle = tempfile.NamedTemporaryFile(prefix="algobot-verified-model-", suffix=".joblib", delete=False)
    try:
        handle.write(body)
        handle.flush()
        return handle.name
    finally:
        handle.close()
