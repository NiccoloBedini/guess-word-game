const input = document.getElementById('answer');

let dictionary; // dizionario (parola : definizione)
let words; // lista delle parole (chiavi del dizionario)
let _word = '';
let _interval;
let _appear = [];
const _time = 5000;

input.addEventListener('keydown', function (event) {
  if (event.key === 'Enter') {
    console.log('Hai premuto Invio!');
    checkGuess();
  }
});

function load() {
  show_word();
}

const checkGuess = () => {
  const guess = document.getElementById('answer').value;
  document.getElementById('answer').value = '';
  if (guess === _word) {
    right();
  } else wrong();
};

// const get_definition = async () => {
//   const url = `https://it.wiktionary.org/w/api.php?action=query&titles=${encodeURIComponent(
//     _word
//   )}&prop=extracts&explaintext=true&format=json&origin=*`;

//   try {
//     const res = await fetch(url);
//     const data = await res.json();

//     const page = data.query.pages[Object.keys(data.query.pages)[0]];

//     if (!page.extract) {
//       console.warn('Nessuna definizione trovata per:', _word);
//       return null;
//     }

//     let text = page.extract;

//     text = text.replace(/\r\n/g, '\n');

//     const righe = text
//       .split('\n')
//       .map((r) => r.trim())
//       .filter(Boolean);

//     let definizione = righe.find(
//       (r) => /^(\(|\d+\.|–|-)/.test(r) && !/^={2,}/.test(r)
//     );

//     if (!definizione && righe.length > 1) {
//       definizione = righe[1] || righe[2];
//     }

//     if (!definizione) return null;

//     definizione = definizione.replace(/\([^)]*\)/g, '').trim();

//     definizione = definizione.replace(/^[-–•\d.]+\s*/, '');

//     definizione = definizione.charAt(0).toUpperCase() + definizione.slice(1);

//     return definizione;
//   } catch (err) {
//     console.error('Errore nel fetch:', err);
//     return null;
//   }
// };

const get_definition = () => {
  return dictionary[_word];
};

const add_letter = () => {
  console.log('tick');

  if (_appear.length < 2) {
    clearInterval(_interval);
    return;
  }
  const index = Math.floor(Math.random() * _appear.length);
  const val = _appear[index];

  _appear = _appear.filter((num) => num !== val);

  document.getElementById(val).textContent = _word[val];
};

const show_word = async () => {
  const random = Math.floor(Math.random() * words.length);
  _word = words[random];
  const visible = document.getElementById('word');

  const definition = await get_definition();
  document.getElementById('definition').textContent = definition;

  _appear = [];

  for (let i = 0; i < _word.length; i++) {
    let letter = document.createElement('div');
    letter.className = 'letter';
    letter.id = '' + i;
    if (i == 0 || i == _word.length - 1) letter.innerText = _word[i];
    else {
      letter.innerText = '_';
      _appear.push(i);
    }
    visible.appendChild(letter);
  }

  console.log(_word);
  _interval = setInterval(add_letter, _time);
};

const erase_word = () => {
  const visible = document.getElementById('word');
  visible.innerHTML = '';
  document.getElementById('definition').textContent = '';
};

function right() {
  if (_interval) clearInterval(_interval);
  const title = document.getElementById('title');
  title.classList.add('right');
  setTimeout(() => title.classList.remove('right'), 500);
  score = document.getElementById('score');
  score.textContent = parseInt(score.textContent) + 1;
  erase_word();
  show_word();
}

function wrong() {
  const answer = document.getElementById('answer');
  answer.classList.add('error');
  const title = document.getElementById('title');
  title.classList.add('error');
  setTimeout(() => {
    input.classList.remove('error');
    title.classList.remove('error');
  }, 500);
}

async function loadDictionary() {
  const res = await fetch('./data/words_def.json');
  dictionary = await res.json();
  words = Object.keys(dictionary);
  console.log(words[1]);
  load();
}
loadDictionary();

//load();
