import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .docx import build_informe_tecnico_docx
from .texto import normalize_text_deep

WD_FORMAT_PDF = 17


def _safe_pdf_name(file_name: str) -> str:
    base = Path(file_name or "informe_tecnico.pdf").name
    if not base.lower().endswith(".pdf"):
        stem = Path(base).stem or "informe_tecnico"
        base = f"{stem}.pdf"
    return base


def _safe_docx_name(file_name: str) -> str:
    stem = Path(file_name or "informe_tecnico.pdf").stem or "informe_tecnico"
    return f"{stem}.docx"




def _convert_with_word_powershell(docx_path: str, pdf_path: str):
    if os.name != "nt":
        return False, "PowerShell COM solo aplica en Windows"

    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if not powershell:
        return False, "PowerShell no está disponible"

    docx_norm = str(Path(docx_path).resolve()).replace("'", "''")
    pdf_norm = str(Path(pdf_path).resolve()).replace("'", "''")
    script = (
        "$ErrorActionPreference = 'Stop';"
        f"$docx = '{docx_norm}';"
        f"$pdf = '{pdf_norm}';"
        "$word = $null; $doc = $null;"
        "try {"
        "  $word = New-Object -ComObject Word.Application;"
        "  $word.Visible = $false;"
        "  $word.DisplayAlerts = 0;"
        "  $doc = $word.Documents.Open($docx, $false, $true);"
        "  try { $doc.Fields.Update() } catch {};"
        "  try { foreach ($sect in $doc.Sections) { foreach ($hdr in $sect.Headers) { try { $hdr.Range.Fields.Update() } catch {} }; foreach ($ftr in $sect.Footers) { try { $ftr.Range.Fields.Update() } catch {} } } } catch {};"
        "  try { $doc.TablesOfContents | ForEach-Object { try { $_.Update() } catch {} } } catch {};"
        f"  $doc.SaveAs([ref] $pdf, [ref] {WD_FORMAT_PDF});"
        "  $doc.Close($false);"
        "  $word.Quit();"
        "} catch {"
        "  if ($doc -ne $null) { try { $doc.Close($false) } catch {} };"
        "  if ($word -ne $null) { try { $word.Quit() } catch {} };"
        "  throw"
        "}"
    )
    try:
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as exc:
        return False, f"Falló la ejecución de PowerShell para Microsoft Word: {exc}"

    if completed.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        return True, "PDF convertido desde el documento Word usando Microsoft Word (PowerShell COM)"

    stderr = (completed.stderr or completed.stdout or "").strip()
    return False, f"Falló la conversión con Microsoft Word (PowerShell COM): {stderr or 'sin detalle'}"

def _convert_with_docx2pdf(docx_path: str, pdf_path: str):
    try:
        from docx2pdf import convert  # type: ignore
    except Exception as exc:
        return False, f"docx2pdf no disponible: {exc}"
    try:
        convert(docx_path, pdf_path)
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return True, "PDF convertido desde Word usando docx2pdf"
        return False, "docx2pdf terminó sin generar el PDF"
    except Exception as exc:
        return False, f"Falló docx2pdf: {exc}"



def _convert_with_word_com_pywin32(docx_path: str, pdf_path: str):
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:
        return False, f"pywin32 no disponible: {exc}"

    word = None
    document = None
    try:
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(Path(docx_path).resolve()), ReadOnly=True)
        # Refrescar TOC + campos antes de exportar a PDF
        try:
            document.Fields.Update()
        except Exception:
            pass
        try:
            for sect in document.Sections:
                for hdr in sect.Headers:
                    try:
                        hdr.Range.Fields.Update()
                    except Exception:
                        pass
                for ftr in sect.Footers:
                    try:
                        ftr.Range.Fields.Update()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            for toc in document.TablesOfContents:
                try:
                    toc.Update()
                except Exception:
                    pass
        except Exception:
            pass
        document.SaveAs(str(Path(pdf_path).resolve()), FileFormat=WD_FORMAT_PDF)
        document.Close(False)
        document = None
        word.Quit()
        word = None
        pythoncom.CoUninitialize()
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return True, "PDF convertido desde el documento Word usando Microsoft Word (pywin32)"
        return False, "Microsoft Word no generó el PDF"
    except Exception as exc:
        try:
            if document is not None:
                document.Close(False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        return False, f"Falló la conversión con Microsoft Word (pywin32): {exc}"



def _convert_with_word_com_comtypes(docx_path: str, pdf_path: str):
    try:
        import comtypes.client  # type: ignore
    except Exception as exc:
        return False, f"comtypes no disponible: {exc}"

    word = None
    document = None
    try:
        word = comtypes.client.CreateObject("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(Path(docx_path).resolve()), ReadOnly=True)
        # Refrescar TOC + campos antes de exportar a PDF
        try:
            document.Fields.Update()
        except Exception:
            pass
        try:
            for sect in document.Sections:
                for hdr in sect.Headers:
                    try:
                        hdr.Range.Fields.Update()
                    except Exception:
                        pass
                for ftr in sect.Footers:
                    try:
                        ftr.Range.Fields.Update()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            for toc in document.TablesOfContents:
                try:
                    toc.Update()
                except Exception:
                    pass
        except Exception:
            pass
        document.SaveAs(str(Path(pdf_path).resolve()), FileFormat=WD_FORMAT_PDF)
        document.Close(False)
        document = None
        word.Quit()
        word = None
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return True, "PDF convertido desde el documento Word usando Microsoft Word (comtypes)"
        return False, "Microsoft Word no generó el PDF"
    except Exception as exc:
        try:
            if document is not None:
                document.Close(False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        return False, f"Falló la conversión con Microsoft Word (comtypes): {exc}"



def _find_soffice_executable():
    candidates = []
    env_path = shutil.which("soffice") or shutil.which("libreoffice")
    if env_path:
        candidates.append(env_path)

    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/bin/soffice",
                "/usr/local/bin/soffice",
                "/snap/bin/libreoffice",
            ]
        )

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None



def _convert_with_soffice(docx_path: str, pdf_path: str):
    soffice = _find_soffice_executable()
    if not soffice:
        return False, "LibreOffice/soffice no está disponible"

    outdir = str(Path(pdf_path).parent.resolve())
    expected_pdf = str(Path(outdir) / (Path(docx_path).stem + ".pdf"))
    command = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        outdir,
        str(Path(docx_path).resolve()),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except Exception as exc:
        return False, f"Falló la ejecución de LibreOffice: {exc}"

    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        return False, f"LibreOffice no pudo convertir el documento: {stderr}"

    if os.path.exists(expected_pdf) and os.path.getsize(expected_pdf) > 0:
        if Path(expected_pdf).resolve() != Path(pdf_path).resolve():
            shutil.move(expected_pdf, pdf_path)
        return True, "PDF convertido desde el documento Word usando LibreOffice"
    return False, "LibreOffice terminó sin generar el PDF"



def _convert_docx_bytes_to_pdf_bytes(docx_bytes: bytes, docx_name: str, pdf_name: str):
    messages = []
    with tempfile.TemporaryDirectory(prefix="informe_tecnico_pdf_") as temp_dir:
        docx_path = str(Path(temp_dir) / _safe_docx_name(docx_name))
        pdf_path = str(Path(temp_dir) / _safe_pdf_name(pdf_name))
        Path(docx_path).write_bytes(docx_bytes)

        converters = []
        if os.name == "nt":
            converters.extend([
                _convert_with_word_com_pywin32,
                _convert_with_word_com_comtypes,
                _convert_with_word_powershell,
                _convert_with_docx2pdf,
                _convert_with_soffice,
            ])
        else:
            converters.extend([
                _convert_with_soffice,
                _convert_with_docx2pdf,
            ])

        for converter in converters:
            ok, message = converter(docx_path, pdf_path)
            messages.append(message)
            if ok and os.path.exists(pdf_path):
                return Path(pdf_path).read_bytes(), message, messages

        return None, "No fue posible convertir el documento Word a PDF automáticamente.", messages



def build_informe_tecnico_pdf(report_model, file_name="informe_tecnico.pdf"):
    report_model = normalize_text_deep(report_model or {})
    """
    Genera el PDF del informe técnico usando como base el mismo DOCX que se exporta.
    La ruta principal es:
    1) construir el DOCX final del informe técnico
    2) convertir ese DOCX a PDF con Microsoft Word o LibreOffice
    """
    result = {
        "success": False,
        "pdf_bytes": None,
        "file_name": _safe_pdf_name(file_name),
        "message": "",
        "source_docx_name": _safe_docx_name(file_name),
        "conversion_log": [],
    }

    try:
        docx_result = build_informe_tecnico_docx(
            report_model=report_model,
            file_name=_safe_docx_name(file_name),
        )
        if not docx_result.get("success") or not docx_result.get("docx_bytes"):
            result["message"] = (
                "No fue posible generar primero el documento Word base del informe técnico. "
                + str(docx_result.get("message") or "")
            ).strip()
            return result

        pdf_bytes, success_message, log_messages = _convert_docx_bytes_to_pdf_bytes(
            docx_bytes=docx_result["docx_bytes"],
            docx_name=docx_result.get("file_name", _safe_docx_name(file_name)),
            pdf_name=_safe_pdf_name(file_name),
        )
        result["conversion_log"] = log_messages
        result["source_docx_name"] = docx_result.get("file_name", _safe_docx_name(file_name))

        if pdf_bytes:
            result["success"] = True
            result["pdf_bytes"] = pdf_bytes
            result["message"] = (
                "PDF del informe técnico generado correctamente a partir del documento Word. "
                + success_message
            ).strip()
            return result

        result["message"] = (
            "No fue posible exportar el PDF directamente desde el documento Word. "
            "Instale Microsoft Word en Windows o LibreOffice para habilitar la conversión automática. "
            + " | ".join([m for m in log_messages if m])
        ).strip()
        return result
    except Exception as exc:
        result["message"] = f"No fue posible generar el PDF del informe técnico desde el documento Word: {exc}"
        return result
