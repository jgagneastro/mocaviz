(() => {
  function saveTable(format, options) {
    const rows = options.rows || [];
    const columns = options.columns || [];
    if (!rows.length || !columns.length) return;
    const filenameBase = options.filenameBase || "mocadb_export";
    if (format === "csv") {
      const csv = [
        columns.join(","),
        ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
      ].join("\n");
      downloadBlob(csv, `${filenameBase}.csv`, "text/csv;charset=utf-8");
    } else if (format === "tsv") {
      const tsv = [
        columns.join("\t"),
        ...rows.map((row) => columns.map((column) => tsvCell(row[column])).join("\t")),
      ].join("\n");
      downloadBlob(tsv, `${filenameBase}.tsv`, "text/tab-separated-values;charset=utf-8");
    } else if (format === "votable") {
      downloadBlob(buildVotable(rows, columns, options), `${filenameBase}.vot`, "application/x-votable+xml;charset=utf-8");
    } else if (format === "fits") {
      downloadBlob(buildFitsTable(rows, columns, options), `${filenameBase}.fits`, "application/fits");
    }
  }

  function buildVotable(rows, columns, options) {
    const numericColumns = asSet(options.numericColumns);
    const tableName = options.tableName || "mocadb_export";
    const resourceName = options.resourceName || "MOCAdb JavaScript export";
    const fieldXml = columns.map((column) => {
      const datatype = numericColumns.has(column) ? "double" : "char";
      const arraysize = datatype === "char" ? ' arraysize="*"' : "";
      return `      <FIELD name="${xmlEscape(column)}" datatype="${datatype}"${arraysize}/>`;
    }).join("\n");
    const rowsXml = rows.map((row) => {
      const cells = columns.map((column) => `          <TD>${xmlEscape(cellText(row[column]))}</TD>`).join("\n");
      return `        <TR>\n${cells}\n        </TR>`;
    }).join("\n");
    return `<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
  <RESOURCE name="${xmlEscape(resourceName)}">
    <TABLE name="${xmlEscape(tableName)}">
${fieldXml}
      <DATA>
        <TABLEDATA>
${rowsXml}
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>
</VOTABLE>
`;
  }

  function buildFitsTable(rows, columns, options) {
    const numericColumns = asSet(options.numericColumns);
    const specs = columns.map((name) => {
      if (numericColumns.has(name)) return { name, form: "D", bytes: 8, numeric: true };
      const width = Math.max(1, ...rows.map((row) => fitsAscii(cellText(row[name])).length));
      return { name, form: `${Math.min(width, 1024)}A`, bytes: Math.min(width, 1024), numeric: false };
    });
    const rowLength = specs.reduce((total, spec) => total + spec.bytes, 0);
    const primary = fitsHeader([
      fitsCard("SIMPLE", true),
      fitsCard("BITPIX", 8),
      fitsCard("NAXIS", 0),
      fitsCard("EXTEND", true),
      fitsEndCard(),
    ]);
    const tableCards = [
      fitsCard("XTENSION", "BINTABLE"),
      fitsCard("BITPIX", 8),
      fitsCard("NAXIS", 2),
      fitsCard("NAXIS1", rowLength),
      fitsCard("NAXIS2", rows.length),
      fitsCard("PCOUNT", 0),
      fitsCard("GCOUNT", 1),
      fitsCard("TFIELDS", specs.length),
    ];
    specs.forEach((spec, index) => {
      tableCards.push(fitsCard(`TTYPE${index + 1}`, spec.name));
      tableCards.push(fitsCard(`TFORM${index + 1}`, spec.form));
    });
    tableCards.push(fitsCard("EXTNAME", options.extName || "MOCA_EXPORT"));
    tableCards.push(fitsEndCard());

    const data = new Uint8Array(paddedLength(rowLength * rows.length));
    const view = new DataView(data.buffer);
    rows.forEach((row, rowIndex) => {
      let offset = rowIndex * rowLength;
      specs.forEach((spec) => {
        if (spec.numeric) {
          const value = Number(row[spec.name]);
          view.setFloat64(offset, Number.isFinite(value) ? value : NaN, false);
        } else {
          data.fill(32, offset, offset + spec.bytes);
          const text = fitsAscii(cellText(row[spec.name])).slice(0, spec.bytes);
          for (let index = 0; index < text.length; index += 1) data[offset + index] = text.charCodeAt(index);
        }
        offset += spec.bytes;
      });
    });
    return new Blob([primary, fitsHeader(tableCards), data], { type: "application/fits" });
  }

  function downloadBlob(content, filename, type) {
    const blob = content instanceof Blob ? content : new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function csvCell(value) {
    const text = cellText(value);
    if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
    return text;
  }

  function tsvCell(value) {
    return cellText(value).replace(/[\t\r\n]+/g, " ");
  }

  function cellText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
    if (Array.isArray(value) || (typeof value === "object" && value !== null)) return JSON.stringify(value);
    return String(value);
  }

  function asSet(values) {
    return values instanceof Set ? values : new Set(values || []);
  }

  function xmlEscape(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");
  }

  function fitsHeader(cards) {
    return asciiBytes(cards.join("").padEnd(paddedLength(cards.length * 80), " "));
  }

  function fitsCard(keyword, value) {
    let textValue;
    if (typeof value === "boolean") {
      textValue = value ? "T" : "F";
    } else if (typeof value === "number") {
      textValue = String(value);
    } else {
      textValue = `'${fitsAscii(value).replace(/'/g, "''")}'`;
    }
    return `${keyword.padEnd(8)}= ${textValue.padStart(20)}`.padEnd(80, " ");
  }

  function fitsEndCard() {
    return "END".padEnd(80, " ");
  }

  function paddedLength(length) {
    return Math.ceil(length / 2880) * 2880;
  }

  function asciiBytes(text) {
    const output = new Uint8Array(text.length);
    for (let index = 0; index < text.length; index += 1) output[index] = text.charCodeAt(index) & 0x7f;
    return output;
  }

  function fitsAscii(value) {
    return String(value ?? "").replace(/[^\x20-\x7e]/g, "?");
  }

  window.MocaExport = {
    saveTable,
    downloadBlob,
    csvCell,
    tsvCell,
  };
})();
