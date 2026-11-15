// Task family names and the one-line question each family asks. Shared by app.js and review.js; edit here.
export const FAMINFO = {
  gc: { name: "Geometry consistency", q: "layout holds as the camera moves", ask: "Move the camera away and back. Is the place still the same place?" },
  if: { name: "Interaction fidelity", q: "each action does what was asked", ask: "Press a key. Does the subject do what was asked, with real contact?" },
  insight: { name: "Insight evolution", q: "an on-screen process keeps going", ask: "Wait and watch. Does a process on screen keep going sensibly?" },
  outsight: { name: "Out-of-sight evolution", q: "hidden things change sensibly", ask: "Look away, then back. Did the hidden part of the world move on sensibly?" }
};
