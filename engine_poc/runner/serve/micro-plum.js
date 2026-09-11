var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// src/loader.ts
import yaml from "js-yaml";

// src/dictParser.ts
function parseDict(schema) {
  const result = [];
  for (const [key, value] of Object.entries(schema)) {
    switch (key) {
      case "import_tables":
        for (const file of value || []) {
          result.push(file + ".dict.yaml");
        }
        break;
      case "vocabulary":
        result.push(value + ".txt");
        break;
    }
  }
  return result.map((file) => [file]);
}

// src/luaParser.ts
import { parse } from "luaparse";

// src/util.ts
function expandLua(file) {
  const match = file.match(/^(lua\/.+)\.lua$/);
  if (match) {
    return [file, `${match[1]}/init.lua`];
  }
  return [file];
}

// src/luaParser.ts
function parseLua(content) {
  const luaFiles = [];
  const ast = parse(content, {
    luaVersion: "5.3",
    onCreateNode(node) {
      if (node.type === "CallExpression") {
        const { base, arguments: args } = node;
        if (base.type === "Identifier" && (base.name === "require" || base.name === "dofile") && args.length === 1) {
          const arg = args[0];
          if (arg.type === "StringLiteral" && arg.raw.match(/'[_a-zA-Z0-9./]+'|"[_a-zA-Z0-9./]+"/)) {
            const module = arg.raw.slice(1, -1);
            luaFiles.push(`lua/${module.replaceAll(".", "/")}.lua`);
          }
        }
      }
    }
  });
  const result = luaFiles.map(expandLua);
  for (const comment of ast.comments || []) {
    const m = comment.raw.match(/@dependency +(.*)/);
    if (!m) {
      continue;
    }
    const filename = m[1];
    result.push([filename]);
  }
  return result;
}

// src/openccParser.ts
function parseOpenCC(config) {
  const result = [];
  const add = (file) => !result.includes(file) && result.push(file);
  add(config.segmentation.dict.file);
  for (const { dict } of config.conversion_chain) {
    const { dicts, file } = dict;
    file && add(file);
    if (dicts) {
      for (const item of dicts) {
        add(item.file);
      }
    }
  }
  return result.map((file) => [file]);
}

// src/schemaParser.ts
function parseSchema(schema) {
  const result = [];
  function parseInclude(obj) {
    for (const [key, value] of Object.entries(obj)) {
      if (key === "__include" || key === "__patch") {
        let values;
        if (typeof value === "string") {
          values = [value];
        } else if (Array.isArray(value)) {
          values = value;
        } else {
          return parseInclude(value);
        }
        for (const v of values) {
          if (typeof v === "string") {
            const i = v.indexOf(":");
            if (i >= 0) {
              let file = v.slice(0, i);
              if (!file.endsWith(".yaml")) {
                file += ".yaml";
              }
              result.push(file);
            }
          } else if (v && typeof v === "object") {
            parseInclude(v);
          }
        }
      } else if (value && typeof value === "object") {
        parseInclude(value);
      }
    }
  }
  parseInclude(schema);
  for (const [key, value] of Object.entries(schema)) {
    switch (key) {
      case "engine":
        for (const component of ["processor", "segmentor", "translator", "filter"]) {
          const name = component + "s";
          if (name in value) {
            const pattern = RegExp(`^lua_${component}@(\\*)?([_a-zA-Z0-9]+(/[_a-zA-Z0-9]+)*)(@[_a-zA-Z0-9]+)?$`);
            for (const item of value[name]) {
              const match = item.match(pattern);
              if (match) {
                if (match[1]) {
                  result.push(`lua/${match[2]}.lua`);
                } else {
                  !result.includes("rime.lua") && result.push("rime.lua");
                }
              }
            }
          }
        }
        break;
      case "translator": {
        if (value.dictionary) {
          const dictYaml = value.dictionary + ".dict.yaml";
          result.push(dictYaml);
        }
        break;
      }
      case "punctuator":
        if (value.import_preset && !["default"].includes(value.import_preset)) {
          result.push(value.import_preset + ".yaml");
        }
        break;
    }
    if (value && typeof value === "object" && "opencc_config" in value) {
      result.push(value.opencc_config);
    }
  }
  return result.map(expandLua);
}
function getBinaryNames(schema) {
  if (schema.translator) {
    const { dictionary, prism } = schema.translator;
    return { dict: dictionary, prism: prism || dictionary };
  }
  return {};
}

// src/loader.ts
var decoder = new TextDecoder("utf-8", { fatal: true });
function u2s(u) {
  return decoder.decode(u);
}
var generic = {
  "rime/rime-emoji": [
    ["emoji_suggestion.yaml"],
    ["opencc/emoji.json"]
  ],
  "rime/rime-essay": [
    ["essay.txt"]
  ],
  "rime/rime-prelude": [
    ["default.yaml"],
    ["key_bindings.yaml"],
    ["punctuation.yaml"],
    ["symbols.yaml"]
  ]
};
var Recipe = class {
  constructor(loader, options) {
    __publicField(this, "loader");
    __publicField(this, "onLoadFailure");
    __publicField(this, "loadedFiles", {});
    this.loader = loader;
    options || (options = {});
    this.onLoadFailure = options.onLoadFailure;
  }
  async loadFileGroup(fileGroup) {
    const errors = [];
    for (const file of fileGroup) {
      if (file === "opencc/emoji.json" && this.loader.repo !== "rime/rime-emoji") {
        return;
      }
      if (file in this.loadedFiles) {
        continue;
      }
      this.loadedFiles[file] = void 0;
      let content;
      try {
        content = await this.loader.loadFile(file);
      } catch (e) {
        errors.push([file, typeof e === "number" ? e : e.message]);
        continue;
      }
      this.loadedFiles[file] = content;
      const promises = [];
      if (file.endsWith(".yaml")) {
        const s = u2s(content);
        let obj;
        if (file.endsWith(".schema.yaml")) {
          try {
            obj = yaml.load(s);
          } catch {
            throw new Error(`Invalid ${file}`);
          }
          const newFileGroups = parseSchema(obj);
          for (const newFileGroup of newFileGroups) {
            promises.push(this.loadFileGroup(newFileGroup.map((newFile) => newFile.endsWith(".json") ? `opencc/${newFile}` : newFile)));
          }
        } else if (file.endsWith(".dict.yaml")) {
          let obj2;
          try {
            obj2 = yaml.loadAll(s)[0];
          } catch {
            const start = s.match(/(^|\n)---\n/)?.index;
            obj2 = yaml.load(s.slice(start, s.indexOf("\n...")));
          }
          const newFileGroups = parseDict(obj2);
          for (const newFileGroup of newFileGroups) {
            promises.push(this.loadFileGroup(newFileGroup));
          }
        }
      } else if (file.endsWith(".json")) {
        const obj = JSON.parse(u2s(content));
        const newFileGroups = parseOpenCC(obj);
        for (const newFileGroup of newFileGroups) {
          promises.push(this.loadFileGroup(newFileGroup.map((newFile) => `opencc/${newFile}`)));
        }
      } else if (file.endsWith(".lua")) {
        const newFileGroups = parseLua(u2s(content));
        for (const newFileGroup of newFileGroups) {
          promises.push(this.loadFileGroup(newFileGroup));
        }
      }
      return Promise.all(promises);
    }
    if (this.onLoadFailure) {
      for (const [url, error] of errors) {
        this.onLoadFailure(url, error);
      }
    }
  }
  async load() {
    if (this.loader.repo in generic) {
      await Promise.all(generic[this.loader.repo].map((fileGroup) => this.loadFileGroup(fileGroup)));
    } else {
      await Promise.all(this.loader.schemaIds.map(async (schemaId) => {
        const file = `${schemaId}.schema.yaml`;
        return this.loadFileGroup([file]);
      }));
    }
    return Object.entries(this.loadedFiles).map(([file, content]) => ({ file, content }));
  }
};

// src/downloader.ts
var builtinOpenCC = [
  "HKVariants.ocd2",
  "HKVariantsRev.ocd2",
  "HKVariantsRevPhrases.ocd2",
  "JPShinjitaiCharacters.ocd2",
  "JPShinjitaiPhrases.ocd2",
  "JPVariants.ocd2",
  "JPVariantsRev.ocd2",
  "STCharacters.ocd2",
  "STPhrases.ocd2",
  "TSCharacters.ocd2",
  "TSPhrases.ocd2",
  "TWPhrases.ocd2",
  "TWPhrasesRev.ocd2",
  "TWVariants.ocd2",
  "TWVariantsRev.ocd2",
  "TWVariantsRevPhrases.ocd2",
  "hk2s.json",
  "hk2t.json",
  "jp2t.json",
  "s2hk.json",
  "s2t.json",
  "s2tw.json",
  "s2twp.json",
  "t2hk.json",
  "t2jp.json",
  "t2s.json",
  "t2tw.json",
  "tw2s.json",
  "tw2sp.json",
  "tw2t.json"
];
for (let i = 0; i < builtinOpenCC.length; ++i) {
  builtinOpenCC[i] = "opencc/" + builtinOpenCC[i];
}
var openccCDN = "https://cdn.jsdelivr.net/npm/@libreservice/my-opencc@0.2.0/dist/";
function matchPlum(target) {
  const match = target.match(/^([-_a-zA-Z0-9]+)(\/[-_a-zA-Z0-9]+)?(@[-_a-zA-Z0-9]+)?$/);
  if (!match) {
    return void 0;
  }
  const repo = match[2] ? match[1] + match[2] : "rime/" + (match[1].startsWith("rime-") ? match[1] : `rime-${match[1]}`);
  const branch = match[3] ? match[3].slice(1) : void 0;
  return { repo, branch, path: "", schema: void 0 };
}
function matchSchema(target) {
  const match = target.match(/(^https?:\/\/)?github\.com\/([-_a-zA-Z0-9]+\/[-_a-zA-Z0-9]+)\/blob\/([-_a-zA-Z0-9]+)\/(([-_a-zA-Z0-9%]+\/)*)([-_a-zA-Z0-9%]+)\.schema\.yaml$/) || target.match(/(^https?:\/\/)?raw\.githubusercontent\.com\/([-_a-zA-Z0-9]+\/[-_a-zA-Z0-9]+)\/([-_a-zA-Z0-9]+)\/(([-_a-zA-Z0-9%]+\/)*)([-_a-zA-Z0-9%]+)\.schema\.yaml$/);
  if (!match) {
    return void 0;
  }
  const repo = match[2];
  const branch = match[3] === "HEAD" ? void 0 : match[3];
  const path = match[4] || "";
  const schema = match[6];
  return { repo, branch, path, schema };
}
function normalizeTarget(target) {
  return matchPlum(target) || matchSchema(target);
}
async function download(url) {
  const response = await fetch(url);
  if (response.ok) {
    return new Uint8Array(await response.arrayBuffer());
  }
  throw response.status;
}
var Downloader = class {
  constructor(target, schemaIds) {
    __publicField(this, "repo");
    __publicField(this, "branch");
    __publicField(this, "path");
    __publicField(this, "prefix");
    __publicField(this, "schemaIds");
    const normalized = normalizeTarget(target);
    if (!normalized) {
      throw new Error("Invalid target");
    }
    this.repo = normalized.repo;
    this.branch = normalized.branch;
    this.path = normalized.path;
    this.prefix = this.getPrefix();
    if (normalized.schema) {
      this.schemaIds = [normalized.schema];
    } else {
      this.schemaIds = schemaIds || [];
    }
  }
  getURL(file) {
    if (builtinOpenCC.includes(file)) {
      return openccCDN + file;
    }
    return this.prefix + file;
  }
  loadFile(file) {
    const url = this.getURL(file);
    return download(url);
  }
};
var GitHubDownloader = class extends Downloader {
  getPrefix() {
    return `https://raw.githubusercontent.com/${this.repo}/${this.branch || "HEAD"}/${this.path}`;
  }
};
var JsDelivrDownloader = class extends Downloader {
  getPrefix() {
    return `https://cdn.jsdelivr.net/gh/${this.repo}${this.branch ? "@" + this.branch : ""}/${this.path}`;
  }
};
export {
  Downloader,
  GitHubDownloader,
  JsDelivrDownloader,
  Recipe,
  getBinaryNames,
  normalizeTarget,
  u2s
};
//# sourceMappingURL=index.js.map
