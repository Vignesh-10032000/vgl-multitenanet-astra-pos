import { registerPlugin } from "@capacitor/core";

const printer = registerPlugin("RestaurantPrinter");

export function openPrinterSetup() {
  return printer.openPrinterSetup();
}

/** Print only the saved receipt markup, with the same bundled styles/fonts as preview. */
export function printDirectReceipt(receipt) {
  const styles = [...document.querySelectorAll('link[rel="stylesheet"], style')]
    .map(node => node.outerHTML).join("\n");
  return printer.printReceipt({
    html: `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; script-src 'none'; base-uri 'none'; form-action 'none'"><meta name="viewport" content="width=device-width,initial-scale=1">${styles}
      <style>html,body{margin:0!important;padding:0!important;min-height:0!important;background:white!important;display:block!important}
      #print-document{display:block!important;width:100%}.receipt-paper{width:100%!important;margin:0!important;box-sizing:border-box!important}</style>
      </head><body><div id="print-document">${receipt}</div></body></html>`,
  });
}
