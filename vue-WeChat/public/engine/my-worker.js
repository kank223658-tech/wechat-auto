var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => {
  __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
  return value;
};
var __accessCheck = (obj, member, msg) => {
  if (!member.has(obj))
    throw TypeError("Cannot " + msg);
};
var __privateGet = (obj, member, getter) => {
  __accessCheck(obj, member, "read from private field");
  return getter ? getter.call(obj) : member.get(obj);
};
var __privateAdd = (obj, member, value) => {
  if (member.has(obj))
    throw TypeError("Cannot add the same private member more than once");
  member instanceof WeakSet ? member.add(obj) : member.set(obj, value);
};
var __privateSet = (obj, member, value, setter) => {
  __accessCheck(obj, member, "write to private field");
  setter ? setter.call(obj, value) : member.set(obj, value);
  return value;
};
var __privateMethod = (obj, member, method) => {
  __accessCheck(obj, member, "access private method");
  return method;
};

// src/LambdaWorker.ts
var TaskSkippedError = class extends Error {
};
var RunningTaskSkippedError = class extends TaskSkippedError {
  constructor(...params) {
    super(...params);
    this.name = "RunningTaskSkippedError";
  }
};
var PendingTaskSkippedError = class extends TaskSkippedError {
  constructor(...params) {
    super(...params);
    this.name = "PendingTaskSkippedError";
  }
};
var RentedBuffer = class {
  constructor(buffer) {
    __publicField(this, "buffer");
    this.buffer = buffer;
  }
};
var _scriptURL, _queue, _running, _commandHandlers, _setUp, setUp_fn, _run, run_fn, _next, next_fn, _schedule, schedule_fn, _killCurrent, killCurrent_fn;
var LambdaWorker = class {
  /**
   * @param scriptURL - The URL of the worker script
   */
  constructor(scriptURL) {
    __privateAdd(this, _setUp);
    __privateAdd(this, _run);
    __privateAdd(this, _next);
    __privateAdd(this, _schedule);
    __privateAdd(this, _killCurrent);
    __publicField(this, "worker");
    __privateAdd(this, _scriptURL, void 0);
    __privateAdd(this, _queue, []);
    __privateAdd(this, _running, null);
    __privateAdd(this, _commandHandlers, {});
    __privateSet(this, _scriptURL, scriptURL);
    this.worker = new Worker(scriptURL);
    __privateMethod(this, _setUp, setUp_fn).call(this);
  }
  /**
   * Registers a worker function in main thread.
   *
   * @param name - The function name
   * @returns A wrapper function for the worker function of the name
   */
  register(name) {
    return (...args) => new Promise((resolve, reject) => __privateMethod(this, _schedule, schedule_fn).call(this, { name, args, transferableIndices: [], resolve, reject }));
  }
  /**
   * Skips the current function.
   *
   * @returns Whether a running function is skipped
   */
  skip() {
    if (!__privateMethod(this, _killCurrent, killCurrent_fn).call(this)) {
      return false;
    }
    this.worker = new Worker(__privateGet(this, _scriptURL));
    __privateMethod(this, _setUp, setUp_fn).call(this);
    __privateMethod(this, _next, next_fn).call(this);
    return true;
  }
  /**
   * Skips all functions.
   *
   * @returns Whether any functions are skipped
   */
  skipAll() {
    if (!__privateMethod(this, _killCurrent, killCurrent_fn).call(this)) {
      return false;
    }
    for (const { reject } of __privateGet(this, _queue)) {
      reject(new PendingTaskSkippedError("Pending task skipped."));
    }
    __privateSet(this, _queue, []);
    this.worker = new Worker(__privateGet(this, _scriptURL));
    __privateMethod(this, _setUp, setUp_fn).call(this);
    return true;
  }
  /**
   * Set callback when receiving signal from a control function.
   *
   * @param name - The name of the control function
   * @param callback The callback
   */
  control(name, callback) {
    __privateGet(this, _commandHandlers)[name] = callback;
  }
};
_scriptURL = new WeakMap();
_queue = new WeakMap();
_running = new WeakMap();
_commandHandlers = new WeakMap();
_setUp = new WeakSet();
setUp_fn = function() {
  this.worker.onmessage = (msg) => {
    const { type } = msg.data;
    if (type === "control") {
      const { name, args } = msg.data;
      const handler = __privateGet(this, _commandHandlers)[name];
      if (handler) {
        handler(...args);
      } else {
        console.warn(`No handler for command ${name}`);
      }
    } else {
      const { args, transferableIndices, resolve, reject } = __privateGet(this, _running);
      __privateSet(this, _running, null);
      __privateMethod(this, _next, next_fn).call(this);
      if (type === "success") {
        const { result, transferables } = msg.data;
        transferables.forEach((arrayBuffer, i) => {
          args[transferableIndices[i]].buffer = arrayBuffer;
        });
        resolve(result);
      } else {
        const { name, message } = msg.data.error;
        const error = new Error(message);
        error.name = name;
        reject(error);
      }
    }
  };
};
_run = new WeakSet();
run_fn = function(task) {
  const { name, args, transferableIndices } = task;
  const transferables = [];
  const unwrappedArgs = args.map((arg, i) => {
    if (arg && arg.constructor === RentedBuffer) {
      transferableIndices.push(i);
      transferables.push(arg.buffer);
      return arg.buffer;
    }
    return arg;
  });
  __privateSet(this, _running, task);
  this.worker.postMessage({ name, args: unwrappedArgs, transferableIndices }, transferables);
};
_next = new WeakSet();
next_fn = function() {
  if (__privateGet(this, _queue).length) {
    const task = __privateGet(this, _queue).shift();
    __privateMethod(this, _run, run_fn).call(this, task);
  }
};
_schedule = new WeakSet();
schedule_fn = function(task) {
  if (__privateGet(this, _running)) {
    __privateGet(this, _queue).push(task);
  } else {
    __privateMethod(this, _run, run_fn).call(this, task);
  }
};
_killCurrent = new WeakSet();
killCurrent_fn = function() {
  if (!__privateGet(this, _running)) {
    return false;
  }
  this.worker.terminate();
  const { reject } = __privateGet(this, _running);
  reject(new RunningTaskSkippedError("Running task skipped."));
  __privateSet(this, _running, null);
  return true;
};

// src/LambdaWrapper.ts
function expose(functions, readyPromise) {
  self.onmessage = async (msg) => {
    await readyPromise;
    const { name, args, transferableIndices } = msg.data;
    const transferables = [];
    let data;
    try {
      const workerFunction = functions[name];
      if (typeof workerFunction !== "function") {
        console.error(`${name} is not an exposed worker function`);
        self.close();
        return;
      }
      const result = await workerFunction(...args);
      args.forEach((arg, i) => transferableIndices.includes(i) && transferables.push(arg));
      data = { type: "success", result, transferables };
    } catch (error) {
      const { message, name: name2 } = error;
      data = {
        type: "error",
        error: {
          message,
          name: name2
        }
      };
    }
    self.postMessage(data, transferables);
  };
}
function control(name) {
  return (...args) => {
    const data = {
      type: "control",
      name,
      args
    };
    self.postMessage(data);
  };
}
function loadWasm(script, options) {
  options = options || {};
  const { url, init } = options;
  return new Promise((resolve) => {
    self.Module = {
      ...options?.Module,
      async onRuntimeInitialized() {
        init && await init();
        resolve(null);
      },
      locateFile(path, prefix) {
        return (url || prefix) + path;
      }
    };
    importScripts((url || "") + script);
  });
}

// src/AsyncFS.ts
function fsOperate(operation, ...args) {
  const result = Module.FS[operation](...args);
  if (operation === "mkdir") {
    return;
  }
  return result;
}
function asyncFS(worker) {
  const fsOperate2 = worker.register("fsOperate");
  return new Proxy({}, {
    get(target, prop) {
      return (...args) => fsOperate2(prop, ...args);
    }
  });
}
export {
  LambdaWorker,
  PendingTaskSkippedError,
  RentedBuffer,
  RunningTaskSkippedError,
  TaskSkippedError,
  asyncFS,
  control,
  expose,
  fsOperate,
  loadWasm
};
//# sourceMappingURL=index.js.map
