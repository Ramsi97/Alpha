export default function Square({ light, piece, pieceColor, onClick }) {
  return (
    <div
      onClick={onClick}
      className={`
        flex items-center justify-center
        w-16 h-16 text-4xl leading-none
        ${light ? 'bg-[#deb887]' : 'bg-[#8b5c2a]'}
      `}
    >
      {piece && (
        <span
          className={
            pieceColor === 'white'
              ? 'text-white [-webkit-text-stroke:1.5px_#2b2b2b]'
              : 'text-[#2b2b2b] [-webkit-text-stroke:1px_#555]'
          }
        >
          {piece}
        </span>
      )}
    </div>
  )
}