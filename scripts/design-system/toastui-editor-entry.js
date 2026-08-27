import Editor from "@toast-ui/editor";

const ns = typeof window !== "undefined" ? window : globalThis;
ns.toastui = ns.toastui || {};
ns.toastui.Editor = Editor;
