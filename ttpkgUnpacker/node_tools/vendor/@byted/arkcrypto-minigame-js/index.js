#!/usr/bin/env node

var Module = require('./dist/bin.js');

// 开发者可关闭 log，防止污染
Module['enableLog'] = true;

Module['_main'] = function () {
    if (Module['enableLog']) {
        console.log('loading wasm...');
    }
}

var hasDone = function () {
    var x = Module['checkDone'];
    return new Promise((resolve, reject) => {
        function wait(times) {
            if (x()) {
                resolve();
                return true;
            } else {
                setTimeout(() => {
                    if (Module['enableLog']) {
                        console.log('waiting...');
                    }
                    wait(times++);
                }, 50 * times);
            }
        }
        wait(1);
    });
};

module.exports = Module;
module.exports.hasDone = hasDone;
