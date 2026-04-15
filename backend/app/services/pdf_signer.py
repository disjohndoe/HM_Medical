"""PAdES digital signature embedding for medical finding PDFs.

Uses AKD smart card via local agent for legally binding signatures when available,
falls back to a local self-signed certificate otherwise.
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields as sig_fields
from pyhanko.sign import signers
from pyhanko_certvalidator.registry import SimpleCertificateStore

from app.services.agent_connection_manager import agent_manager

logger = logging.getLogger(__name__)

# Cache the local signer so we don't regenerate the cert on every request
_local_signer: signers.SimpleSigner | None = None

# Map agent JOSE algorithm -> pyHanko digest algorithm
_AGENT_ALG_TO_DIGEST: dict[str, str] = {
    "RS256": "sha256",
    "ES256": "sha256",
    "ES384": "sha384",
    "ES512": "sha512",
}


def _get_local_signer() -> signers.SimpleSigner:
    """Create or return a cached self-signed signer for local PDF signing."""
    global _local_signer
    if _local_signer is not None:
        return _local_signer

    # Generate RSA key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Build self-signed certificate
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "HR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HM Digital Medical (TEST)"),
        x509.NameAttribute(NameOID.COMMON_NAME, "HM Digital Test Signing Certificate"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2024, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 12, 31, tzinfo=UTC))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=False,
                content_commitment=True, data_encipherment=False,
                key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    # Export to PKCS#12 bytes
    pkcs12_bytes = serialization.pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.NoEncryption(),
    )

    _local_signer = signers.SimpleSigner.load_pkcs12_data(pkcs12_bytes, other_certs=[])
    logger.info("Local PDF signer initialized with self-signed certificate")
    return _local_signer


class AgentPdfSigner(signers.Signer):
    """pyHanko Signer that delegates raw signing to the local agent's AKD smart card.

    Retrieves the X.509 certificate from the agent, then uses the agent's
    sign_raw (NCryptSignHash) for the actual cryptographic operation.
    pyHanko handles CMS/PAdES wrapping automatically.
    """

    def __init__(
        self,
        tenant_id: UUID,
        cert_der: bytes,
        agent_algorithm: str,
    ):
        cert = asn1_x509.Certificate.load(cert_der)
        cert_store = SimpleCertificateStore()
        cert_store.register(cert)
        self._tenant_id = tenant_id
        self._agent_algorithm = agent_algorithm
        super().__init__(
            signing_cert=cert,
            cert_registry=cert_store,
        )

    async def async_sign_raw(
        self, data: bytes, digest_algorithm: str, dry_run: bool = False
    ) -> bytes:
        """Sign raw data via the agent's smart card.

        pyHanko passes DER-encoded signed attributes as `data`.
        The agent hashes and signs via NCryptSignHash.
        """
        if dry_run:
            return b"\x00" * 256

        data_b64 = base64.b64encode(data).decode("ascii")
        result = await agent_manager.sign_raw(
            self._tenant_id,
            data_base64=data_b64,
            algorithm=self._agent_algorithm,
            timeout=30.0,
        )
        if "error" in result:
            raise RuntimeError(f"Agent signing failed: {result['error']}")
        return base64.b64decode(result.get("signature", ""))


def _can_use_agent_signing(tenant_id: UUID) -> bool:
    """Check if a connected agent with card is available for this tenant."""
    conn = agent_manager.get_any_connected(tenant_id)
    return conn is not None and conn.card_inserted


async def _sign_with_agent(
    pdf_bytes: bytes,
    *,
    tenant_id: UUID,
    doctor_name: str = "",
    reason: str = "",
    location: str = "",
) -> bytes:
    """Sign PDF using the AKD smart card via the local agent."""
    cert_info = await agent_manager.get_cert_info(tenant_id, timeout=15.0)
    if "error" in cert_info:
        raise RuntimeError(f"Agent cert info failed: {cert_info['error']}")

    cert_der_b64 = cert_info.get("cert_der_base64")
    if not cert_der_b64:
        raise RuntimeError("Agent did not return certificate DER")

    agent_algorithm = cert_info.get("algorithm", "RS256")
    signer = AgentPdfSigner(
        tenant_id=tenant_id,
        cert_der=base64.b64decode(cert_der_b64),
        agent_algorithm=agent_algorithm,
    )

    reader = PdfFileReader(BytesIO(pdf_bytes))
    w = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
    page_count = int(reader.root["/Pages"]["/Count"])
    last_page = max(0, page_count - 1)

    sig_field = sig_fields.SigFieldSpec(
        sig_field_name="DoctorSignature",
        on_page=last_page,
    )

    digest = _AGENT_ALG_TO_DIGEST.get(agent_algorithm, "sha256")
    meta = signers.PdfSignatureMetadata(
        field_name="DoctorSignature",
        md_algorithm=digest,
        reason=reason,
        location=location,
        name=doctor_name,
    )

    output = BytesIO()
    await signers.async_sign_pdf(w, meta, signer=signer, new_field_spec=sig_field, output=output)

    signed_bytes = output.getvalue()
    logger.info(
        "PDF signed (AKD smart card) for %s — %d -> %d bytes, alg=%s",
        doctor_name, len(pdf_bytes), len(signed_bytes), agent_algorithm,
    )
    return signed_bytes


async def sign_pdf(
    pdf_bytes: bytes,
    *,
    tenant_id: UUID | None = None,
    doctor_name: str = "",
    reason: str = "Digitalno potpisani medicinski nalaz",
    location: str = "",
) -> bytes:
    """Sign a PDF with a PAdES digital signature.

    If a connected agent with an inserted AKD smart card is available,
    uses it for a legally binding signature (napredni elektronički potpis).
    Otherwise falls back to the local self-signed certificate.
    """
    if tenant_id is not None and _can_use_agent_signing(tenant_id):
        try:
            return await _sign_with_agent(
                pdf_bytes,
                tenant_id=tenant_id,
                doctor_name=doctor_name,
                reason=reason,
                location=location,
            )
        except Exception:
            logger.exception(
                "Agent PDF signing failed for tenant %s, falling back to local",
                tenant_id,
            )

    return await _sign_local(
        pdf_bytes, doctor_name=doctor_name, reason=reason, location=location,
    )


async def _sign_local(
    pdf_bytes: bytes,
    *,
    doctor_name: str = "",
    reason: str = "",
    location: str = "",
) -> bytes:
    """Sign PDF using local self-signed certificate."""
    signer = _get_local_signer()

    reader = PdfFileReader(BytesIO(pdf_bytes))
    w = IncrementalPdfFileWriter(BytesIO(pdf_bytes))

    # Determine page count for placing signature on last page
    page_count = int(reader.root["/Pages"]["/Count"])
    last_page = max(0, page_count - 1)

    # Invisible signature — the doctor name and signature line are already
    # in the PDF footer rendered by pdf_generator.py. We embed the digital
    # signature as an invisible field so Adobe Reader shows "Signed by..."
    # in the signature panel without overlapping the footer layout.
    sig_field = sig_fields.SigFieldSpec(
        sig_field_name="DoctorSignature",
        on_page=last_page,
    )

    meta = signers.PdfSignatureMetadata(
        field_name="DoctorSignature",
        md_algorithm="sha256",
        reason=reason,
        location=location,
        name=doctor_name,
    )

    output = BytesIO()
    await signers.async_sign_pdf(
        w,
        meta,
        signer=signer,
        new_field_spec=sig_field,
        output=output,
    )

    signed_bytes = output.getvalue()
    logger.info(
        "PDF signed (local certificate) for %s — %d → %d bytes",
        doctor_name, len(pdf_bytes), len(signed_bytes),
    )
    return signed_bytes
