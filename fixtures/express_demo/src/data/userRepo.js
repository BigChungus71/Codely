// Static Express fixture only. Never execute.
const sqlite3 = require('sqlite3');

function lookupById(userId) {
  const db = sqlite3;
  return db.query('SELECT * FROM users WHERE id = ' + userId);
}

module.exports = { lookupById };
