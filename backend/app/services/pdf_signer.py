"""PAdES digital signature embedding for medical finding PDFs.

Uses a local self-signed certificate for tamper-evident PDF signatures.
CEZIH remote signing (via AKD smart card) is handled separately by dispatcher.sign_document().
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from io import BytesIO

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields as sig_fields
from pyhanko.sign import signers

logger = logging.getLogger(__name__)

# Cache the local signer so we don't regenerate the cert on every request
_local_signer: signers.SimpleSigner | None = None


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


async def sign_pdf(
    pdf_bytes: bytes,
    *,
    doctor_name: str = "",
    reason: str = "Digitalno potpisani medicinski nalaz",
    location: str = "",
) -> bytes:
    """Sign a PDF with a PAdES digital signature using a local certificate.

    Returns the signed PDF bytes.
    """
    return await _sign_local(pdf_bytes, doctor_name=doctor_name, reason=reason, location=location)


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
