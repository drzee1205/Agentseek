const normalizeAnswer = (answer) => {
  return answer
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[.,!?]/g, '');
};

export { normalizeAnswer };
