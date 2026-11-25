// Static Express fixture only. Never execute.
const express = require('express');
const userService = require('../services/userService');

const router = express.Router();

router.get('/api/users', (req, res) => {
  res.cookie('session', 'static-value', { httpOnly: false, secure: true });
  return res.json(userService.findUser(req.query.id));
});

router.get('/go', (req, res) => res.redirect(req.query.next));

module.exports = router;
