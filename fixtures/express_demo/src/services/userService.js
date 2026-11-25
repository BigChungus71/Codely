// Static Express fixture only. Never execute.
const userRepo = require('../data/userRepo');

function findUser(userId) {
  return userRepo.lookupById(userId);
}

module.exports = { findUser };
